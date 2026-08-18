// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// buildCtx holds the resolved paths the build commands need. It replaces the
// Makefile's REPO_ROOT / DOCKER_RUN machinery.
type buildCtx struct {
	scriptsRoot string // the libsmb2-scripts checkout (holds scripts/, docker/, tui/)
	repoRoot    string // the dart_smb2 package (build outputs land here)
	settings    userSettings
}

const dockerImage = "libsmb2-builder"

func newBuildCtx() (*buildCtx, error) {
	sr, err := findScriptsRoot()
	if err != nil {
		return nil, err
	}
	rr, err := resolveRepoRoot(sr)
	if err != nil {
		return nil, err
	}
	return &buildCtx{scriptsRoot: sr, repoRoot: rr, settings: loadSettings()}, nil
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

// resolveRepoRoot finds the dart_smb2 package: $DART_SMB2_ROOT, or the
// sibling checkout next to libsmb2-scripts.
func resolveRepoRoot(scriptsRoot string) (string, error) {
	if env := os.Getenv("DART_SMB2_ROOT"); env != "" {
		if !fileExists(filepath.Join(env, "pubspec.yaml")) {
			return "", fmt.Errorf("DART_SMB2_ROOT does not contain pubspec.yaml: %s", env)
		}
		return env, nil
	}
	cand := filepath.Join(filepath.Dir(scriptsRoot), "dart_smb2")
	if fileExists(filepath.Join(cand, "pubspec.yaml")) {
		return cand, nil
	}
	return "", fmt.Errorf("cannot locate dart_smb2 — clone it next to libsmb2-scripts or set DART_SMB2_ROOT")
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
		cmd := exec.Command("docker", "build", "--platform=linux/amd64",
			"-t", dockerImage, "./docker/")
		cmd.Dir = c.scriptsRoot
		return cmd

	case kDocker:
		args := []string{"run", "--rm", "--platform=linux/amd64",
			"-e", "DART_SMB2_ROOT=/repo",
		}
		for _, kv := range append(c.knobEnv(), t.env...) {
			args = append(args, "-e", kv)
		}
		args = append(args,
			"-v", c.repoRoot+":/repo",
			"-v", c.scriptsRoot+":/scripts",
			"-w", "/scripts",
			dockerImage,
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

// dockerImageMissing reports whether the build-env image needs building.
func dockerImageMissing() bool {
	err := exec.Command("docker", "image", "inspect", dockerImage).Run()
	return err != nil
}

// expand resolves keys → concrete targets: aggregates flatten (depth-first,
// deduped), and the docker-image step is prepended once when any requested
// target needs the container and the image is missing.
func (c *buildCtx) expand(keys []string) ([]Target, error) {
	seen := map[string]bool{}
	var out []Target
	var walk func(key string) error
	walk = func(key string) error {
		t, ok := targetByKey(key)
		if !ok {
			return fmt.Errorf("unknown target %q (try: ./build list)", key)
		}
		if t.kind == kAggregate {
			for _, m := range t.members {
				if err := walk(m); err != nil {
					return err
				}
			}
			return nil
		}
		if !t.Available() {
			return fmt.Errorf("target %q: %s", key, t.unavailReason())
		}
		if !seen[t.Key] {
			seen[t.Key] = true
			out = append(out, t)
		}
		return nil
	}
	for _, k := range keys {
		if err := walk(strings.TrimSpace(k)); err != nil {
			return nil, err
		}
	}

	needImage := false
	for _, t := range out {
		if t.needsDocker() {
			needImage = true
			break
		}
	}
	if needImage && !seen["docker-image"] && dockerImageMissing() {
		img, _ := targetByKey("docker-image")
		out = append([]Target{img}, out...)
	}
	return out, nil
}
