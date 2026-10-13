// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "testing"

func testCtx() *buildCtx {
	return &buildCtx{scriptsRoot: "/tmp/s"}
}

func TestExpandUnknownTarget(t *testing.T) {
	if _, _, err := testCtx().expand([]string{"nope"}); err == nil {
		t.Fatal("expected an error for an unknown target")
	}
}

func TestExpandFlattensAggregates(t *testing.T) {
	// android is a kNative aggregate → expands to its three ABIs without
	// touching docker.
	prevOS := hostOS
	hostOS = "linux"
	defer func() { hostOS = prevOS }()

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
	prevOS := hostOS
	hostOS = "linux"
	defer func() { hostOS = prevOS }()

	got, _, err := testCtx().expand([]string{"android-x86_64", "android-x86_64"})
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("expanded to %d targets, want 1 (deduped)", len(got))
	}
}

func TestExpandRejectsUnavailable(t *testing.T) {
	prevOS := hostOS
	hostOS = "linux"
	defer func() { hostOS = prevOS }()

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
	// everything else (Android, Linux, Windows, the manifest) still runs.
	prevOS := hostOS
	hostOS = "linux"
	defer func() { hostOS = prevOS }()

	got, skipped, err := testCtx().expand([]string{"android", "all"})
	if err != nil {
		t.Fatal(err)
	}
	wantSkipped := []string{"macos: needs macOS + Xcode", "ios: needs macOS + Xcode"}
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
	for _, k := range []string{"android-arm64-v8a", "linux-x86_64", "windows-arm64", "manifest"} {
		if !keys[k] {
			t.Errorf("%s missing from the expansion of all", k)
		}
	}
	if keys["macos"] || keys["ios"] {
		t.Error("an Apple target was kept on a linux host")
	}
	if got[len(got)-1].Key != "manifest" {
		t.Errorf("last target = %q, want manifest", got[len(got)-1].Key)
	}

	// Named explicitly, an unavailable target still fails, even after an
	// aggregate skipped it.
	if _, _, err := testCtx().expand([]string{"all", "macos"}); err == nil {
		t.Fatal("expected an error: macos named on a linux host")
	}
}
