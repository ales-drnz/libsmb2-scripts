// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func testCtx() *buildCtx {
	return &buildCtx{scriptsRoot: "/tmp/s"}
}

// onHost simulates a host OS and whether the Android NDK is installed, for
// the rest of the test.
func onHost(t *testing.T, goos string, ndk bool) {
	t.Helper()
	prevOS, prevNDK := hostOS, ndkFound
	hostOS = goos
	ndkFound = func() bool { return ndk }
	t.Cleanup(func() { hostOS, ndkFound = prevOS, prevNDK })
}

func TestExpandUnknownTarget(t *testing.T) {
	if _, _, err := testCtx().expand([]string{"nope"}); err == nil {
		t.Fatal("expected an error for an unknown target")
	}
}

func TestExpandFlattensAggregates(t *testing.T) {
	// android is a kNative aggregate → expands to its three ABIs without
	// touching docker.
	onHost(t, "linux", true)

	got, _, err := testCtx().expand([]string{"android"})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"android-arm64-v8a", "android-armeabi-v7a", "android-x86_64"}
	if len(got) != len(want) {
		t.Fatalf("expanded to %d targets, want %d", len(got), len(want))
	}
	for i, k := range want {
		if got[i].Key != k {
			t.Errorf("member %d = %q, want %q", i, got[i].Key, k)
		}
	}
}

func TestExpandDeduplicates(t *testing.T) {
	onHost(t, "linux", true)

	got, _, err := testCtx().expand([]string{"android-x86_64", "android-x86_64"})
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("expanded to %d targets, want 1 (deduped)", len(got))
	}
}

func TestExpandRejectsUnavailable(t *testing.T) {
	onHost(t, "linux", true)

	if _, _, err := testCtx().expand([]string{"macos"}); err == nil {
		t.Fatal("expected an error: macos target on a linux host")
	}
}

func TestEveryAggregateMemberExists(t *testing.T) {
	for _, tg := range allTargets() {
		for _, mkey := range tg.members {
			if _, ok := targetByKey(mkey); !ok {
				t.Errorf("aggregate %q references unknown member %q", tg.Key, mkey)
			}
		}
	}
}

func TestExpandSkipsUnavailableAggregateMembers(t *testing.T) {
	// `./build all` on Linux: macOS and iOS are left out with a reason,
	// Android, Linux and Windows still build, and the manifest, which
	// would describe a partial release, is left out too.
	onHost(t, "linux", true)

	got, skipped, err := testCtx().expand([]string{"android", "all"})
	if err != nil {
		t.Fatal(err)
	}
	wantSkipped := []string{"macos: needs macOS + Xcode", "ios: needs macOS + Xcode",
		"manifest: the release would be partial (run ./build manifest once all nine binaries are in release_builds/)"}
	if len(skipped) != len(wantSkipped) {
		t.Fatalf("skipped %q, want %q", skipped, wantSkipped)
	}
	for i := range wantSkipped {
		if skipped[i] != wantSkipped[i] {
			t.Errorf("skipped[%d] = %q, want %q", i, skipped[i], wantSkipped[i])
		}
	}
	keys := map[string]bool{}
	for _, tg := range got {
		keys[tg.Key] = true
	}
	for _, k := range []string{"android-arm64-v8a", "linux-x86_64", "windows-arm64"} {
		if !keys[k] {
			t.Errorf("%s missing from the expansion of all", k)
		}
	}
	if keys["macos"] || keys["ios"] {
		t.Error("an Apple target was kept on a linux host")
	}
	if keys["manifest"] {
		t.Error("all kept the manifest although macOS and iOS were skipped")
	}

	// Named explicitly, an unavailable target still fails, even after an
	// aggregate skipped it.
	if _, _, err := testCtx().expand([]string{"all", "macos"}); err == nil {
		t.Fatal("expected an error: macos named on a linux host")
	}
}

func TestExpandAllWritesTheManifestWhenNothingIsSkipped(t *testing.T) {
	onHost(t, "darwin", true)
	got, skipped, err := testCtx().expand([]string{"all"})
	if err != nil {
		t.Fatal(err)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped %q on a macOS host with the NDK", skipped)
	}
	if got[len(got)-1].Key != "manifest" {
		t.Errorf("last target = %q, want manifest", got[len(got)-1].Key)
	}
}

func TestExpandKeepsAManifestNamedExplicitly(t *testing.T) {
	onHost(t, "linux", true)
	got, _, err := testCtx().expand([]string{"all", "manifest"})
	if err != nil {
		t.Fatal(err)
	}
	if got[len(got)-1].Key != "manifest" {
		t.Errorf("last target = %q, want manifest (named explicitly)", got[len(got)-1].Key)
	}
}

func TestExpandAllWithoutTheNDKSkipsAndroid(t *testing.T) {
	// The NDK is missing: all goes on with Linux and Windows instead of
	// stopping at the first Android target.
	onHost(t, "linux", false)
	got, skipped, err := testCtx().expand([]string{"all"})
	if err != nil {
		t.Fatal(err)
	}
	reason := "needs Android NDK " + ndkVersion
	for _, k := range []string{"android-arm64-v8a", "android-armeabi-v7a", "android-x86_64"} {
		found := false
		for _, s := range skipped {
			if s == k+": "+reason {
				found = true
			}
		}
		if !found {
			t.Errorf("skipped %q, want %q", skipped, k+": "+reason)
		}
	}
	keys := map[string]bool{}
	for _, tg := range got {
		keys[tg.Key] = true
	}
	for _, k := range []string{"linux-x86_64", "linux-aarch64", "windows-x86_64", "windows-arm64"} {
		if !keys[k] {
			t.Errorf("%s missing from the expansion of all", k)
		}
	}
	for k := range keys {
		if strings.HasPrefix(k, "android-") || k == "manifest" {
			t.Errorf("%s kept without the NDK", k)
		}
	}

	// Named explicitly, an Android target still fails.
	if _, _, err := testCtx().expand([]string{"android-x86_64"}); err == nil || !strings.Contains(err.Error(), reason) {
		t.Errorf("android-x86_64 without the NDK: err = %v, want %q", err, reason)
	}
}

func TestExpandRejectsAnEmptyAggregateNamedExplicitly(t *testing.T) {
	// Every member unavailable: an error, not a silent exit 0.
	onHost(t, "linux", false)
	_, _, err := testCtx().expand([]string{"android"})
	if err == nil || !strings.Contains(err.Error(), "nothing in it can run") {
		t.Fatalf("android without the NDK: err = %v, want an error", err)
	}
	onHost(t, "windows", true)
	if _, _, err := testCtx().expand([]string{"android"}); err == nil {
		t.Fatal("android on a windows host: want an error")
	}
	// Partly available, it skips with a line.
	got, skipped, err := testCtx().expand([]string{"all"})
	if err != nil {
		t.Fatalf("all on a windows host: %v", err)
	}
	if len(got) == 0 || len(skipped) == 0 {
		t.Fatalf("all on a windows host: %d targets, skipped %q", len(got), skipped)
	}
}

func TestNDKVersionMatchesTheAndroidScript(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("..", "scripts", "build_libsmb2_android.sh"))
	if err != nil {
		t.Fatal(err)
	}
	m := regexp.MustCompile(`NDK_VERSION="\$\{NDK_VERSION:-([^}]+)\}"`).FindSubmatch(data)
	if m == nil {
		t.Fatal("NDK_VERSION default not found in build_libsmb2_android.sh")
	}
	if string(m[1]) != ndkVersion {
		t.Errorf("ndkVersion = %q, build_libsmb2_android.sh pins %q", ndkVersion, m[1])
	}
}

func TestFindAndroidNDK(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	for _, v := range []string{"NDK_HOME", "ANDROID_NDK_HOME", "ANDROID_NDK", "NDK_VERSION", "ALLOW_ANY_NDK"} {
		t.Setenv(v, "")
	}
	if findAndroidNDK() {
		t.Fatal("found an NDK in an empty home")
	}

	ndk := filepath.Join(home, "Android", "Sdk", "ndk", ndkVersion)
	if err := os.MkdirAll(ndk, 0o755); err != nil {
		t.Fatal(err)
	}
	write := func(rev string) {
		if err := os.WriteFile(filepath.Join(ndk, "source.properties"),
			[]byte("Pkg.Desc = Android NDK\nPkg.Revision = "+rev+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write(ndkVersion)
	if !findAndroidNDK() {
		t.Error("the pinned NDK under ~/Android/Sdk/ndk was not found")
	}

	other := filepath.Join(home, "other-ndk")
	if err := os.MkdirAll(other, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(other, "source.properties"), []byte("Pkg.Revision = 27.0.1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("NDK_HOME", other)
	if findAndroidNDK() {
		t.Error("NDK_HOME with another version was accepted")
	}
	t.Setenv("ALLOW_ANY_NDK", "1")
	if !findAndroidNDK() {
		t.Error("ALLOW_ANY_NDK=1 did not accept NDK_HOME")
	}
	t.Setenv("NDK_HOME", filepath.Join(home, "missing"))
	if findAndroidNDK() {
		t.Error("a missing NDK_HOME was accepted")
	}
}
