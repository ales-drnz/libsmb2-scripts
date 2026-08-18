// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "runtime"

type tkind int

const (
	kNative    tkind = iota // bash script on the host
	kDocker                 // bash script inside the libsmb2-builder container
	kImage                  // docker build of the build-env image
	kAggregate              // expands to other targets
)

// Target is one buildable / publishable step. It carries everything needed to
// construct its command at run time — no Makefile in the loop.
type Target struct {
	Key       string
	Label     string
	Group     string
	Desc      string // one-line "what it does"
	AppleOnly bool   // needs macOS + Xcode
	InMenu    bool   // shown in the interactive selector

	kind    tkind
	script  string
	env     []string // extra "K=V" pairs (ARCHS / ABIS selectors)
	members []string // for kAggregate
}

// hostOS is the OS the orchestrator runs on. A package var so tests can
// simulate other hosts.
var hostOS = runtime.GOOS

// Available reports whether this target can run on the current host:
//   - Apple targets (macOS / iOS) need macOS + Xcode.
//   - Other native scripts are bash + Unix tools — fine on macOS / Linux /
//     WSL, not on native Windows.
//   - Docker targets (Linux / Windows cross builds) only need Docker.
func (t Target) Available() bool {
	switch {
	case t.AppleOnly:
		return hostOS == "darwin"
	case t.kind == kNative:
		return hostOS != "windows"
	default:
		return true
	}
}

// unavailReason explains, for the UI, why a target can't run here ("" when it
// can).
func (t Target) unavailReason() string {
	if t.Available() {
		return ""
	}
	if t.AppleOnly {
		return "needs macOS + Xcode"
	}
	if t.kind == kNative {
		return "needs a macOS/Linux host (Unix build script)"
	}
	return "unavailable on this host"
}

func (t Target) needsDocker() bool { return t.kind == kDocker }

// fullLabel is the unambiguous name for flat views (logs / CLI), where there
// is no section header to provide the OS context.
func (t Target) fullLabel() string {
	if t.Group == "Tools" || t.Group == "Docker" {
		return t.Label
	}
	return t.Group + " " + t.Label
}

func allTargets() []Target {
	const (
		sMac     = "scripts/build_libsmb2_macos.sh"
		sIOS     = "scripts/build_libsmb2_ios.sh"
		sAndroid = "scripts/build_libsmb2_android.sh"
		sLinux   = "scripts/build_libsmb2_linux.sh"
		sWin     = "scripts/build_libsmb2_windows.sh"
	)
	return []Target{
		// ── macOS / iOS (xcframeworks lipo into one artifact → single target) ──
		{Key: "macos", Label: "all (universal)", Group: "macOS", AppleOnly: true, InMenu: true, kind: kNative, script: sMac,
			Desc: "arm64 + x86_64 universal xcframework"},
		{Key: "ios", Label: "all (device+sim)", Group: "iOS", AppleOnly: true, InMenu: true, kind: kNative, script: sIOS,
			Desc: "device arm64 + simulator arm64/x86_64 xcframework"},

		// ── Android (native — NDK on the host) ──
		{Key: "android-arm64-v8a", Label: "arm64-v8a", Group: "Android", InMenu: true, kind: kNative, script: sAndroid, env: []string{"ABIS=arm64-v8a"}},
		{Key: "android-armeabi-v7a", Label: "armeabi-v7a", Group: "Android", InMenu: true, kind: kNative, script: sAndroid, env: []string{"ABIS=armeabi-v7a"}},
		{Key: "android-x86_64", Label: "x86_64", Group: "Android", InMenu: true, kind: kNative, script: sAndroid, env: []string{"ABIS=x86_64"}},
		{Key: "android", Label: "all", Group: "Android", InMenu: true, kind: kAggregate,
			members: []string{"android-arm64-v8a", "android-armeabi-v7a", "android-x86_64"}},

		// ── Linux (Docker — any host) ──
		{Key: "linux-x86_64", Label: "x86_64", Group: "Linux", InMenu: true, kind: kDocker, script: sLinux, env: []string{"ARCHS=x86_64"}},
		{Key: "linux-aarch64", Label: "aarch64", Group: "Linux", InMenu: true, kind: kDocker, script: sLinux, env: []string{"ARCHS=aarch64"}},
		{Key: "linux", Label: "all", Group: "Linux", InMenu: true, kind: kAggregate,
			members: []string{"linux-x86_64", "linux-aarch64"}},

		// ── Windows (Docker — any host) ──
		{Key: "windows-x86_64", Label: "x86_64", Group: "Windows", InMenu: true, kind: kDocker, script: sWin, env: []string{"ARCHS=x86_64"}},
		{Key: "windows-arm64", Label: "arm64", Group: "Windows", InMenu: true, kind: kDocker, script: sWin, env: []string{"ARCHS=arm64"}},
		{Key: "windows", Label: "all", Group: "Windows", InMenu: true, kind: kAggregate,
			members: []string{"windows-x86_64", "windows-arm64"}},

		// ── Publish / validate ──
		{Key: "checksums", Label: "Checksums", Group: "Tools", InMenu: true, kind: kNative, script: "scripts/generate_checksums.sh",
			Desc: "install built libs into dart_smb2 + refresh its SHA-256s"},
		{Key: "verify", Label: "Verify", Group: "Tools", InMenu: true, kind: kNative, script: "scripts/verify_binaries.sh",
			Desc: "dlopen + FFI-symbol audit of the host-loadable binaries"},
		{Key: "bump", Label: "Bump", Group: "Tools", InMenu: false, kind: kNative, script: "scripts/bump_version.sh",
			Desc: "propagate LIB_VERSION / RELEASE_VERSION into dart_smb2"},

		// ── Non-menu (CLI / internal) ──
		{Key: "docker-image", Label: "Build the build-env image", Group: "Docker", InMenu: false, kind: kImage},

		// ── Aggregates (CLI convenience) ──
		{Key: "desktop-all", Label: "All desktop targets", Group: "Aggregate", InMenu: false, kind: kAggregate, members: []string{"linux", "windows"}},
		{Key: "all", Label: "Everything + checksums", Group: "Aggregate", InMenu: false, kind: kAggregate,
			members: []string{"macos", "ios", "android", "desktop-all", "checksums"}},
	}
}

func targetByKey(key string) (Target, bool) {
	for _, t := range allTargets() {
		if t.Key == key {
			return t, true
		}
	}
	return Target{}, false
}

// menuTargets returns the targets shown in the interactive selector.
func menuTargets() []Target {
	var out []Target
	for _, t := range allTargets() {
		if t.InMenu {
			out = append(out, t)
		}
	}
	return out
}
