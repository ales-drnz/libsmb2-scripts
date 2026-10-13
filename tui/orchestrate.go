// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// buildCtx holds the resolved paths the build commands need. It replaces the
// Makefile's DOCKER_RUN machinery. Building needs only this repo: the
// binaries, manifest.json and SHA256SUMS land in release_builds/.
type buildCtx struct {
	scriptsRoot string // the libsmb2-scripts checkout (holds scripts/, docker/, tui/)
	settings    userSettings
}

func newBuildCtx() (*buildCtx, error) {
	sr, err := findScriptsRoot()
	if err != nil {
		return nil, err
	}
	return &buildCtx{scriptsRoot: sr, settings: loadSettings()}, nil
}

// imageRepo is the image name of one docker/Dockerfile stage.
func imageRepo(stage string) string { return "libsmb2-build-" + stage }

// imageRef tags a stage image with a hash of docker/Dockerfile, so editing
// the Dockerfile makes the orchestrator build a fresh image instead of
// reusing one with an older toolchain.
func (c *buildCtx) imageRef(stage string) string {
	tag := "latest"
	if data, err := os.ReadFile(filepath.Join(c.scriptsRoot, "docker", "Dockerfile")); err == nil {
		sum := sha256.Sum256(data)
		tag = hex.EncodeToString(sum[:6])
	}
	return imageRepo(stage) + ":" + tag
}

// dockerPlatform pins the linux stage to amd64: its gcc is the x86_64
// compiler and aarch64 is the cross one, so on an arm64 host it runs under
// emulation. The windows (llvm-mingw for either host arch) and verify
// stages run natively.
func dockerPlatform(stage string) []string {
	if stage == "linux" {
		return []string{"--platform=linux/amd64"}
	}
	return nil
}

// findScriptsRoot walks up from the executable and the CWD looking for the
// libsmb2-scripts checkout (identified by scripts/shared/_versions.sh).
func findScriptsRoot() (string, error) {
	roots := []string{mustGetwd()}
	if exe, err := os.Executable(); err == nil {
		roots = append(roots, filepath.Dir(exe))
	}
	for _, r := range roots {
		for dir := r; dir != "/" && dir != "."; dir = filepath.Dir(dir) {
			if fileExists(filepath.Join(dir, "scripts", "shared", "_versions.sh")) {
				return dir, nil
			}
		}
	}
	return "", fmt.Errorf("cannot locate the libsmb2-scripts root (scripts/shared/_versions.sh not found upwards of %s)", mustGetwd())
}

func mustGetwd() string {
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	return wd
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// knobEnv returns the session knobs as K=V pairs, from settings plus the
// environment (env wins, so `JOBS=2 ./build linux` still works).
func (c *buildCtx) knobEnv() []string {
	var env []string
	if v := os.Getenv("JOBS"); v != "" {
		env = append(env, "JOBS="+v)
	}
	if c.settings.KeepBuild || os.Getenv("KEEP_BUILD") == "1" {
		env = append(env, "KEEP_BUILD=1")
	}
	if c.settings.ForceDownload || os.Getenv("FORCE_DOWNLOAD") == "1" {
		env = append(env, "FORCE_DOWNLOAD=1")
	}
	return env
}

// command builds the *exec.Cmd for one concrete (non-aggregate) target.
func (c *buildCtx) command(t Target) *exec.Cmd {
	switch t.kind {
	case kImage:
		args := append([]string{"build"}, dockerPlatform(t.image)...)
		args = append(args, "--target", t.image, "-t", c.imageRef(t.image), "./docker/")
		cmd := exec.Command("docker", args...)
		cmd.Dir = c.scriptsRoot
		return cmd

	case kDocker:
		args := append([]string{"run", "--rm"}, dockerPlatform(t.image)...)
		// Run as the calling user, so release_builds/ stays theirs.
		if hostOS != "windows" {
			args = append(args, "-u", fmt.Sprintf("%d:%d", os.Getuid(), os.Getgid()))
		}
		for _, kv := range append(c.knobEnv(), t.env...) {
			args = append(args, "-e", kv)
		}
		args = append(args,
			"-v", c.scriptsRoot+":/scripts",
			"-w", "/scripts",
			c.imageRef(t.image),
			"bash", "./"+t.script,
		)
		cmd := exec.Command("docker", args...)
		cmd.Dir = c.scriptsRoot
		return cmd

	default: // kNative
		cmd := exec.Command("bash", "./"+t.script)
		cmd.Dir = c.scriptsRoot
		cmd.Env = append(os.Environ(), append(c.knobEnv(), t.env...)...)
		return cmd
	}
}

// imageMissing reports whether a stage image needs building.
func (c *buildCtx) imageMissing(stage string) bool {
	return exec.Command("docker", "image", "inspect", c.imageRef(stage)).Run() != nil
}

// expand resolves keys → concrete targets: aggregates flatten (depth-first,
// deduped), and the docker-image-<stage> step of every missing image a
// requested target runs in is prepended once. A target this host cannot run
// is an error when it was asked for by name, and is left out when it comes
// from an aggregate (`./build all` on Linux skips macOS and iOS): skipped
// lists those, as "<key>: <reason>".
func (c *buildCtx) expand(keys []string) (out []Target, skipped []string, err error) {
	seen, skippedSeen := map[string]bool{}, map[string]bool{}
	var walk func(key string, fromAggregate bool) error
	walk = func(key string, fromAggregate bool) error {
		t, ok := targetByKey(key)
		if !ok {
			return fmt.Errorf("unknown target %q (try: ./build list)", key)
		}
		if t.kind == kAggregate {
			for _, m := range t.members {
				if err := walk(m, true); err != nil {
					return err
				}
			}
			return nil
		}
		if !t.Available() {
			if !fromAggregate {
				return fmt.Errorf("target %q: %s", key, t.unavailReason())
			}
			if !skippedSeen[t.Key] {
				skippedSeen[t.Key] = true
				skipped = append(skipped, t.Key+": "+t.unavailReason())
			}
			return nil
		}
		if !seen[t.Key] {
			seen[t.Key] = true
			out = append(out, t)
		}
		return nil
	}
	for _, k := range keys {
		if err := walk(strings.TrimSpace(k), false); err != nil {
			return nil, nil, err
		}
	}

	var images []Target
	for _, t := range out {
		if !t.needsDocker() {
			continue
		}
		key := "docker-image-" + t.image
		if seen[key] || !c.imageMissing(t.image) {
			continue
		}
		seen[key] = true
		img, _ := targetByKey(key)
		images = append(images, img)
	}
	out = append(images, out...)
	return out, skipped, nil
}
