// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// A SwiftPM-style file has BOTH a local and a remote region; exactly one must be
// active (uncommented) per mode, and round-tripping must be lossless.
func TestLibToggleSwiftBothRegions(t *testing.T) {
	// The commented (inactive) region is written in NORMALIZED style — the
	// comment token sits after each line's natural indentation, exactly as the
	// toggler produces — so local↔remote is byte-for-byte reversible.
	const src = `    targets: [
        // smb2kit:local:begin
        .binaryTarget(
            name: "libsmb2",
            path: "Frameworks/libsmb2.xcframework"),
        // smb2kit:local:end
        // smb2kit:remote:begin
        // .binaryTarget(
            // name: "libsmb2",
            // url: "https://example/libsmb2.zip",
            // checksum: "abc"),
        // smb2kit:remote:end
    ]`

	// → remote: local commented, remote uncommented.
	rem, _, regions := libToggleContent(src, "//", libRemote)
	if regions != 2 {
		t.Fatalf("expected 2 regions, saw %d", regions)
	}
	if !strings.Contains(rem, "\n            url: \"https://example/libsmb2.zip\",\n") {
		t.Errorf("remote mode should activate the url line:\n%s", rem)
	}
	if !strings.Contains(rem, "\n            // path: \"Frameworks/libsmb2.xcframework\"),\n") {
		t.Errorf("remote mode should comment the local path line:\n%s", rem)
	}
	// Marker lines must be untouched.
	if !strings.Contains(rem, "// smb2kit:local:begin") || !strings.Contains(rem, "// smb2kit:remote:end") {
		t.Errorf("marker lines must never be toggled:\n%s", rem)
	}

	// → local: should restore the original byte-for-byte.
	loc, _, _ := libToggleContent(rem, "//", libLocal)
	if loc != src {
		t.Errorf("local↔remote round-trip not lossless:\n--- got ---\n%s\n--- want ---\n%s", loc, src)
	}

	// Idempotent: re-applying the same mode yields no edits.
	if _, changes, _ := libToggleContent(loc, "//", libLocal); changes != 0 {
		t.Errorf("re-applying local should be a no-op, got %d changes", changes)
	}
}

// A CMake-style file has ONLY a remote region (local use is unconditional):
// local mode comments the download block, remote mode uncomments it.
func TestLibToggleCMakeRemoteOnly(t *testing.T) {
	const src = `set(_BUNDLED_SMB2 "x")
# smb2kit:remote:begin
if(DOWNLOAD_NEEDED)
  file(DOWNLOAD "url" "${_BUNDLED_SMB2}")
endif()
# smb2kit:remote:end
add_library(x)`

	loc, changes, regions := libToggleContent(src, "#", libLocal)
	if regions != 1 {
		t.Fatalf("expected 1 region, saw %d", regions)
	}
	if changes == 0 {
		t.Fatal("local mode should comment the download block")
	}
	if !strings.Contains(loc, "\n# if(DOWNLOAD_NEEDED)\n") || !strings.Contains(loc, "\n  # file(DOWNLOAD") {
		t.Errorf("local mode should comment every body line (indent-preserving):\n%s", loc)
	}
	// Unrelated lines outside the region are untouched.
	if !strings.Contains(loc, "\nadd_library(x)") || !strings.Contains(loc, "set(_BUNDLED_SMB2 \"x\")\n") {
		t.Errorf("lines outside the region must not change:\n%s", loc)
	}
	// Back to remote restores the original.
	rem, _, _ := libToggleContent(loc, "#", libRemote)
	if rem != src {
		t.Errorf("remote round-trip not lossless:\n%s", rem)
	}
}

// libSetMode writes every consumer file and reports per-file results; a file
// missing its markers is a hard error, not a silent pass.
func TestLibSetModeOnDisk(t *testing.T) {
	root := t.TempDir()
	write := func(rel, content string) {
		p := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	// Lay down every toggle file with a minimal remote region (+ a local region
	// for the Swift manifests).
	for _, f := range libToggleFiles() {
		c := f.token + " smb2kit:remote:begin\nDOWNLOAD()\n" + f.token + " smb2kit:remote:end\n"
		if strings.HasSuffix(f.rel, "Package.swift") {
			c = f.token + " smb2kit:local:begin\nLOCAL()\n" + f.token + " smb2kit:local:end\n" + c
		}
		write(f.rel, c)
	}

	entries, err := libSetMode(root, libLocal)
	if err != nil {
		t.Fatalf("libSetMode(local) error: %v", err)
	}
	if len(entries) != len(libToggleFiles()) {
		t.Fatalf("expected %d entries, got %d", len(libToggleFiles()), len(entries))
	}
	for _, e := range entries {
		if e.Status != "ok" {
			t.Errorf("%s: status %q (%s)", e.Label, e.Status, e.Message)
		}
	}
	// In local mode the download line must be commented everywhere.
	for _, f := range libToggleFiles() {
		data, err := os.ReadFile(filepath.Join(root, f.rel))
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(data), f.token+" DOWNLOAD()") {
			t.Errorf("%s: DOWNLOAD() not commented in local mode:\n%s", f.rel, data)
		}
	}

	// A file with no markers is a hard error.
	write("linux/CMakeLists.txt", "no markers here\n")
	if _, err := libSetMode(root, libLocal); err == nil {
		t.Error("expected an error when a consumer file lacks smb2kit markers")
	}
}

// libFileMode reads the active region of a single file; libDetectMode folds the
// per-file modes into one verdict (mixed when they disagree).
func TestLibDetectMode(t *testing.T) {
	swiftLocal := "// smb2kit:local:begin\n.binaryTarget(path: \"x\"),\n// smb2kit:local:end\n" +
		"// smb2kit:remote:begin\n// .binaryTarget(url: \"y\"),\n// smb2kit:remote:end\n"
	swiftRemote := "// smb2kit:local:begin\n// .binaryTarget(path: \"x\"),\n// smb2kit:local:end\n" +
		"// smb2kit:remote:begin\n.binaryTarget(url: \"y\"),\n// smb2kit:remote:end\n"
	cmakeRemote := "# smb2kit:remote:begin\nfile(DOWNLOAD)\n# smb2kit:remote:end\n"
	cmakeLocal := "# smb2kit:remote:begin\n# file(DOWNLOAD)\n# smb2kit:remote:end\n"

	if got := libFileMode(swiftLocal, "//"); got != "local" {
		t.Errorf("swiftLocal = %q, want local", got)
	}
	if got := libFileMode(swiftRemote, "//"); got != "remote" {
		t.Errorf("swiftRemote = %q, want remote", got)
	}
	if got := libFileMode(cmakeRemote, "#"); got != "remote" {
		t.Errorf("cmakeRemote = %q, want remote", got)
	}
	if got := libFileMode(cmakeLocal, "#"); got != "local" {
		t.Errorf("cmakeLocal = %q, want local", got)
	}

	// Whole package: write every toggle file, then confirm detect agrees.
	root := t.TempDir()
	writeAll := func(mode libMode) {
		for _, f := range libToggleFiles() {
			// Token-correct markers per file: a remote region everywhere, plus a
			// local region for the SwiftPM manifests.
			base := f.token + " smb2kit:remote:begin\nDOWNLOAD()\n" + f.token + " smb2kit:remote:end\n"
			if strings.HasSuffix(f.rel, "Package.swift") {
				base = f.token + " smb2kit:local:begin\nLOCAL()\n" + f.token + " smb2kit:local:end\n" + base
			}
			p := filepath.Join(root, f.rel)
			if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(p, []byte(base), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		if _, err := libSetMode(root, mode); err != nil {
			t.Fatalf("setMode: %v", err)
		}
	}
	writeAll(libLocal)
	if got := libDetectMode(root); got != "local" {
		t.Errorf("detect after setMode(local) = %q, want local", got)
	}
	writeAll(libRemote)
	if got := libDetectMode(root); got != "remote" {
		t.Errorf("detect after setMode(remote) = %q, want remote", got)
	}
	// Force a disagreement: flip one file back to local.
	one := filepath.Join(root, "linux/CMakeLists.txt")
	data, err := os.ReadFile(one)
	if err != nil {
		t.Fatal(err)
	}
	out, _, _ := libToggleContent(string(data), "#", libLocal)
	if err := os.WriteFile(one, []byte(out), 0o644); err != nil {
		t.Fatal(err)
	}
	if got := libDetectMode(root); got != "mixed" {
		t.Errorf("detect with one file flipped = %q, want mixed", got)
	}
}

// libClean removes present binaries and reports absent ones as skipped.
func TestLibClean(t *testing.T) {
	root := t.TempDir()
	// Create two of the slots (one file, one xcframework directory).
	soPath := filepath.Join(root, "linux/libs/x86_64/libsmb2.so")
	if err := os.MkdirAll(filepath.Dir(soPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(soPath, []byte("elf"), 0o644); err != nil {
		t.Fatal(err)
	}
	xcf := filepath.Join(root, "macos/dart_smb2/Frameworks/libsmb2.xcframework")
	if err := os.MkdirAll(xcf, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(xcf, "Info.plist"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	entries, err := libClean(root)
	if err != nil {
		t.Fatalf("libClean error: %v", err)
	}
	var removed, skipped int
	for _, e := range entries {
		switch e.Status {
		case "ok":
			removed++
		case "skipped":
			skipped++
		}
	}
	if removed != 2 {
		t.Errorf("expected 2 removed, got %d", removed)
	}
	if skipped != len(libBinaryPaths())-2 {
		t.Errorf("expected %d skipped, got %d", len(libBinaryPaths())-2, skipped)
	}
	if fileExists(soPath) || fileExists(xcf) {
		t.Error("clean must remove both the .so file and the xcframework directory")
	}
}
