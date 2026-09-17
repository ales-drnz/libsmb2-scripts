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

// Libs source switch — same mechanism as libmpv-scripts. dart_smb2 consumes
// the prebuilt libsmb2 per platform either from a bundled local copy or by
// downloading it from its GitHub Releases. Four of the five build systems
// (CMake on Linux/Windows, Gradle on Android, CocoaPods on iOS/macOS) already
// "use local if present, else download" — but they also re-download over a
// local copy whose SHA-256 does not match, silently replacing a locally built
// binary. SwiftPM is a hard either/or. Each consumer file wraps its toggleable
// region in
//
//	<comment> smb2kit:<mode>:begin   …region…   <comment> smb2kit:<mode>:end
//
// markers, and the three Libs actions comment / uncomment those regions:
//
//   - local  → use the bundled binary only, never download (download regions
//     commented; SwiftPM's local `path:` region active). Runs the Checksums
//     install first so the bundled binaries + their SHAs are refreshed.
//   - remote → download from GitHub when the local copy is absent / stale
//     (download regions active; SwiftPM's `url:+checksum:` region active).
//   - clean  → delete the bundled binaries from every platform slot, so a
//     remote build has nothing stale to fall back to.
//
// The marker lines themselves are always comments and are never toggled.

const libMarkerPrefix = "smb2kit:"

type libMode int

const (
	libLocal libMode = iota
	libRemote
)

func (m libMode) String() string {
	if m == libRemote {
		return "remote"
	}
	return "local"
}

// libToggleFile is one consumer build file plus its line-comment token.
type libToggleFile struct {
	rel   string
	token string
}

// libToggleFiles lists every dart_smb2 file whose smb2kit: regions the Libs
// actions drive. Kept in lockstep with the markers in the consumer repo.
func libToggleFiles() []libToggleFile {
	return []libToggleFile{
		{"ios/dart_smb2/Package.swift", "//"},
		{"macos/dart_smb2/Package.swift", "//"},
		{"ios/dart_smb2.podspec", "#"},
		{"macos/dart_smb2.podspec", "#"},
		{"android/build.gradle.kts", "//"},
		{"linux/CMakeLists.txt", "#"},
		{"windows/CMakeLists.txt", "#"},
	}
}

// libBinaryPath is one bundled-binary slot in the consumer package, removed by
// the clean action.
type libBinaryPath struct {
	label string
	rel   string
}

func libBinaryPaths() []libBinaryPath {
	return []libBinaryPath{
		{"macos xcframework", "macos/dart_smb2/Frameworks/libsmb2.xcframework"},
		{"ios xcframework", "ios/dart_smb2/Frameworks/libsmb2.xcframework"},
		{"android arm64-v8a", "android/src/main/jniLibs/arm64-v8a/libsmb2.so"},
		{"android armeabi-v7a", "android/src/main/jniLibs/armeabi-v7a/libsmb2.so"},
		{"android x86_64", "android/src/main/jniLibs/x86_64/libsmb2.so"},
		{"linux x86_64", "linux/libs/x86_64/libsmb2.so"},
		{"linux aarch64", "linux/libs/aarch64/libsmb2.so"},
		{"windows x86_64", "windows/libs/x86_64/libsmb2.dll"},
		{"windows arm64", "windows/libs/arm64/libsmb2.dll"},
	}
}

// libEntry is the per-file (or per-slot) result of a Libs action.
type libEntry struct {
	Label   string
	Status  string // "ok" | "skipped" | "error"
	Message string
	Changes int // lines commented / uncommented
}

// ── marker-driven comment/uncomment ─────────────────────────────────────────

func leadingWS(s string) string {
	return s[:len(s)-len(strings.TrimLeft(s, " \t"))]
}

// lineCommented reports whether line's first non-whitespace run is the token.
func lineCommented(line, token string) bool {
	return strings.HasPrefix(strings.TrimLeft(line, " \t"), token)
}

// commentLine prefixes the comment token to a line, preserving its indentation.
// Blank and already-commented lines are returned unchanged (idempotent).
func commentLine(line, token string) string {
	if strings.TrimSpace(line) == "" || lineCommented(line, token) {
		return line
	}
	ws := leadingWS(line)
	return ws + token + " " + line[len(ws):]
}

// uncommentLine strips one leading comment token (and at most one following
// space), preserving indentation. Non-commented lines are returned unchanged.
func uncommentLine(line, token string) string {
	if !lineCommented(line, token) {
		return line
	}
	ws := leadingWS(line)
	rest := strings.TrimPrefix(line[len(ws):], token)
	rest = strings.TrimPrefix(rest, " ")
	return ws + rest
}

// parseLibMarker returns (mode, edge, true) when line is a
// `smb2kit:<mode>:<edge>` marker for the given comment token.
func parseLibMarker(line, token string) (mode, edge string, ok bool) {
	t := strings.TrimLeft(line, " \t")
	if !strings.HasPrefix(t, token) {
		return "", "", false
	}
	t = strings.TrimSpace(strings.TrimPrefix(t, token))
	if !strings.HasPrefix(t, libMarkerPrefix) {
		return "", "", false
	}
	parts := strings.Split(t, ":")
	if len(parts) != 3 || (parts[1] != "local" && parts[1] != "remote") ||
		(parts[2] != "begin" && parts[2] != "end") {
		return "", "", false
	}
	return parts[1], parts[2], true
}

// libToggleContent rewrites content so the regions tagged with the target mode
// are uncommented (active) and all other smb2kit regions are commented
// (inert). It returns the new content, the number of changed lines, and the
// number of marker regions it saw (0 ⇒ the file has no smb2kit markers).
func libToggleContent(content, token string, mode libMode) (string, int, int) {
	lines := strings.Split(content, "\n")
	cur := "" // mode of the region we're inside, "" when outside
	changes, regions := 0, 0
	for i, line := range lines {
		if m, edge, ok := parseLibMarker(line, token); ok {
			if edge == "begin" {
				cur, regions = m, regions+1
			} else {
				cur = ""
			}
			continue // marker lines are never toggled
		}
		if cur == "" {
			continue
		}
		var nl string
		if cur == mode.String() {
			nl = uncommentLine(line, token)
		} else {
			nl = commentLine(line, token)
		}
		if nl != line {
			lines[i] = nl
			changes++
		}
	}
	return strings.Join(lines, "\n"), changes, regions
}

// ── current-mode detection ──────────────────────────────────────────────────

// libFileMode reports the mode one consumer file is currently in by checking
// which of its smb2kit regions is active (uncommented):
//   - both local+remote regions (SwiftPM): the active one wins; both/neither
//     active ⇒ "mixed".
//   - only a remote region (CMake / Gradle / podspec): active ⇒ "remote",
//     commented ⇒ "local" (local use is unconditional there).
//
// Returns "unknown" when the file has no smb2kit markers.
func libFileMode(content, token string) string {
	cur := ""
	var hasLocal, hasRemote, localActive, remoteActive bool
	for _, line := range strings.Split(content, "\n") {
		if mode, edge, ok := parseLibMarker(line, token); ok {
			if edge == "begin" {
				cur = mode
				if mode == "local" {
					hasLocal = true
				} else {
					hasRemote = true
				}
			} else {
				cur = ""
			}
			continue
		}
		if cur == "" || strings.TrimSpace(line) == "" {
			continue
		}
		if !lineCommented(line, token) { // an active (uncommented) body line
			if cur == "local" {
				localActive = true
			} else {
				remoteActive = true
			}
		}
	}
	switch {
	case hasLocal && hasRemote:
		switch {
		case localActive && !remoteActive:
			return "local"
		case remoteActive && !localActive:
			return "remote"
		default:
			return "mixed"
		}
	case hasRemote:
		if remoteActive {
			return "remote"
		}
		return "local"
	case hasLocal:
		if localActive {
			return "local"
		}
		return "remote"
	default:
		return "unknown"
	}
}

// libDetectMode inspects every consumer file and returns the package's overall
// libs source: "local", "remote", "mixed" (files disagree — e.g. mid-switch or
// hand-edited), or "unknown" (a file is missing / unmarked).
func libDetectMode(repoRoot string) string {
	seen := ""
	for _, f := range libToggleFiles() {
		data, err := os.ReadFile(filepath.Join(repoRoot, f.rel))
		if err != nil {
			return "unknown"
		}
		m := libFileMode(string(data), f.token)
		if m == "mixed" || m == "unknown" {
			return m
		}
		if seen == "" {
			seen = m
		} else if seen != m {
			return "mixed"
		}
	}
	if seen == "" {
		return "unknown"
	}
	return seen
}

// libSetMode toggles every consumer file to the given mode and returns a
// per-file result plus an aggregate error if any file failed.
func libSetMode(repoRoot string, mode libMode) ([]libEntry, error) {
	var entries []libEntry
	var failed int
	for _, f := range libToggleFiles() {
		e := libEntry{Label: f.rel}
		path := filepath.Join(repoRoot, f.rel)
		data, err := os.ReadFile(path)
		if err != nil {
			e.Status, e.Message = "error", "not found"
			failed++
			entries = append(entries, e)
			continue
		}
		out, changes, regions := libToggleContent(string(data), f.token, mode)
		if regions == 0 {
			e.Status, e.Message = "error", "no "+libMarkerPrefix+" markers"
			failed++
			entries = append(entries, e)
			continue
		}
		if out != string(data) {
			if err := os.WriteFile(path, []byte(out), 0o644); err != nil {
				e.Status, e.Message = "error", err.Error()
				failed++
				entries = append(entries, e)
				continue
			}
		}
		e.Status, e.Changes = "ok", changes
		if changes == 0 {
			e.Message = "already " + mode.String()
		}
		entries = append(entries, e)
	}
	if failed > 0 {
		return entries, fmt.Errorf("%d consumer file(s) could not be switched to %s — is dart_smb2 at %s up to date?", failed, mode, repoRoot)
	}
	return entries, nil
}

// libClean removes the bundled libsmb2 from every platform slot in the
// consumer package, returning a per-slot result.
func libClean(repoRoot string) ([]libEntry, error) {
	var entries []libEntry
	var failed int
	for _, b := range libBinaryPaths() {
		e := libEntry{Label: b.label}
		path := filepath.Join(repoRoot, b.rel)
		if !fileExists(path) {
			e.Status, e.Message = "skipped", "already absent"
			entries = append(entries, e)
			continue
		}
		if err := os.RemoveAll(path); err != nil {
			e.Status, e.Message = "error", err.Error()
			failed++
			entries = append(entries, e)
			continue
		}
		e.Status, e.Message = "ok", "removed"
		entries = append(entries, e)
	}
	if failed > 0 {
		return entries, fmt.Errorf("%d bundled binary(s) could not be removed", failed)
	}
	return entries, nil
}

// ── action entry points (hidden `_lib*` subcommands, run as kSelf targets) ──

// runLibAction runs one Libs action and prints a plain-text summary through
// logf. lib-local first runs the Checksums install best-effort: binaries that
// were not built on this host (e.g. the xcframeworks on Linux) are reported by
// the script and left alone, and the mode switch still happens.
func runLibAction(ctx *buildCtx, key string, logf func(string)) error {
	var (
		entries []libEntry
		err     error
		title   string
	)
	switch key {
	case "lib-local":
		logf("=== Checksums: install built libs into dart_smb2 ===")
		cmd := exec.Command("bash", "./scripts/generate_checksums.sh")
		cmd.Dir = ctx.scriptsRoot
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		if cerr := cmd.Run(); cerr != nil {
			logf("  (checksums incomplete — continuing with the libs that were installed)")
		}
		logf("")
		title = "use local libsmb2 (no GitHub download)"
		entries, err = libSetMode(ctx.repoRoot, libLocal)
	case "lib-remote":
		title = "use remote libsmb2 (download from GitHub when absent)"
		entries, err = libSetMode(ctx.repoRoot, libRemote)
	case "lib-clean":
		title = "clean bundled libsmb2 from dart_smb2"
		entries, err = libClean(ctx.repoRoot)
	default:
		return fmt.Errorf("unknown libs action: %s", key)
	}

	logf("=== dart_smb2: " + title + " ===")
	for _, e := range entries {
		switch e.Status {
		case "ok":
			detail := e.Message
			if detail == "" {
				detail = fmt.Sprintf("%d line(s) changed", e.Changes)
			}
			logf(fmt.Sprintf("  ✓ %s: %s", e.Label, detail))
		case "skipped":
			logf(fmt.Sprintf("  · %s: %s", e.Label, e.Message))
		case "error":
			logf(fmt.Sprintf("  ✗ %s: %s", e.Label, e.Message))
		}
	}
	if err == nil && key != "lib-clean" {
		logf("  libs source is now: " + libDetectMode(ctx.repoRoot))
	}
	return err
}
