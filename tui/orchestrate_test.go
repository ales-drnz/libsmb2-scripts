// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "testing"

func testCtx() *buildCtx {
	return &buildCtx{scriptsRoot: "/tmp/s", repoRoot: "/tmp/r"}
}

func TestExpandUnknownTarget(t *testing.T) {
	if _, err := testCtx().expand([]string{"nope"}); err == nil {
		t.Fatal("expected an error for an unknown target")
	}
}

func TestExpandFlattensAggregates(t *testing.T) {
	// android is a kNative aggregate → expands to its three ABIs without
	// touching docker.
	prevOS := hostOS
	hostOS = "linux"
	defer func() { hostOS = prevOS }()

	got, err := testCtx().expand([]string{"android"})
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

	got, err := testCtx().expand([]string{"android-x86_64", "android-x86_64"})
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

	if _, err := testCtx().expand([]string{"macos"}); err == nil {
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
