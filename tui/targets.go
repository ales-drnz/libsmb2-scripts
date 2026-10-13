// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

type tkind int

const (
	kNative    tkind = iota // bash script on the host
	kDocker                 // bash script inside a docker/Dockerfile stage image
	kImage                  // docker build of one stage image
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
	NeedsNDK  bool   // needs the pinned Android NDK on the host
	InMenu    bool   // shown in the interactive selector

	kind    tkind
	script  string
	env     []string // extra "K=V" pairs (ARCHS / ABIS selectors)
	members []string // for kAggregate
	image   string   // for kDocker / kImage: the docker/Dockerfile stage
}

// hostOS is the OS the orchestrator runs on. A package var so tests can
// simulate other hosts.
var hostOS = runtime.GOOS

// ndkVersion is the Android NDK build_libsmb2_android.sh is pinned to (its
// NDK_VERSION default; a test keeps the two equal).
const ndkVersion = "28.2.13676358"

// ndkFound reports whether build_libsmb2_android.sh will find a usable NDK.
// A package var so tests can simulate either case.
var ndkFound = findAndroidNDK

// findAndroidNDK repeats build_libsmb2_android.sh's lookup: NDK_HOME, then
// ANDROID_NDK_HOME, then ANDROID_NDK, else the usual SDK locations of
// NDK_VERSION (default ndkVersion); the NDK's source.properties must name
// that version unless ALLOW_ANY_NDK=1.
func findAndroidNDK() bool {
	version := os.Getenv("NDK_VERSION")
	if version == "" {
		version = ndkVersion
	}
	ndk := ""
	for _, v := range []string{"NDK_HOME", "ANDROID_NDK_HOME", "ANDROID_NDK"} {
		if ndk = os.Getenv(v); ndk != "" {
			break
		}
	}
	if ndk == "" {
		home, _ := os.UserHomeDir()
		for _, d := range []string{
			filepath.Join(home, "Library", "Android", "sdk", "ndk", version),
			filepath.Join(home, "Android", "Sdk", "ndk", version),
			"/opt/android-ndk-" + version,
			"/usr/local/lib/android/sdk/ndk/" + version,
		} {
			if st, err := os.Stat(d); err == nil && st.IsDir() {
				ndk = d
				break
			}
		}
	}
	if st, err := os.Stat(ndk); ndk == "" || err != nil || !st.IsDir() {
		return false
	}
	if os.Getenv("ALLOW_ANY_NDK") == "1" {
		return true
	}
	data, err := os.ReadFile(filepath.Join(ndk, "source.properties"))
	if err != nil {
		return false
	}
	for _, line := range strings.Split(string(data), "\n") {
		if k, v, ok := strings.Cut(line, "="); ok && strings.TrimSpace(k) == "Pkg.Revision" {
			return strings.TrimSpace(v) == version
		}
	}
	return false
}

// Available reports whether this target can run on the current host:
//   - Apple targets (macOS / iOS) need macOS + Xcode.
//   - Other native scripts are bash + Unix tools — fine on macOS / Linux /
//     WSL, not on native Windows; Android also needs the pinned NDK.
//   - Docker targets (Linux / Windows cross builds) only need Docker.
func (t Target) Available() bool {
	switch {
	case t.AppleOnly:
		return hostOS == "darwin"
	case t.kind == kNative:
		return hostOS != "windows" && (!t.NeedsNDK || ndkFound())
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
	if t.kind == kNative && hostOS == "windows" {
		return "needs a macOS/Linux host (Unix build script)"
	}
	if t.NeedsNDK {
		version := os.Getenv("NDK_VERSION")
		if version == "" {
			version = ndkVersion
		}
		return "needs Android NDK " + version
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
		{Key: "android-arm64-v8a", Label: "arm64-v8a", Group: "Android", InMenu: true, NeedsNDK: true, kind: kNative, script: sAndroid, env: []string{"ABIS=arm64-v8a"}},
		{Key: "android-armeabi-v7a", Label: "armeabi-v7a", Group: "Android", InMenu: true, NeedsNDK: true, kind: kNative, script: sAndroid, env: []string{"ABIS=armeabi-v7a"}},
		{Key: "android-x86_64", Label: "x86_64", Group: "Android", InMenu: true, NeedsNDK: true, kind: kNative, script: sAndroid, env: []string{"ABIS=x86_64"}},
		{Key: "android", Label: "all", Group: "Android", InMenu: true, kind: kAggregate,
			members: []string{"android-arm64-v8a", "android-armeabi-v7a", "android-x86_64"}},

		// ── Linux (Docker — any host; the ubuntu:20.04 stage keeps glibc 2.31) ──
		{Key: "linux-x86_64", Label: "x86_64", Group: "Linux", InMenu: true, kind: kDocker, image: "linux", script: sLinux, env: []string{"ARCHS=x86_64"}},
		{Key: "linux-aarch64", Label: "aarch64", Group: "Linux", InMenu: true, kind: kDocker, image: "linux", script: sLinux, env: []string{"ARCHS=aarch64"}},
		{Key: "linux", Label: "all", Group: "Linux", InMenu: true, kind: kAggregate,
			members: []string{"linux-x86_64", "linux-aarch64"}},

		// ── Windows (Docker — any host) ──
		{Key: "windows-x86_64", Label: "x86_64", Group: "Windows", InMenu: true, kind: kDocker, image: "windows", script: sWin, env: []string{"ARCHS=x86_64"}},
		{Key: "windows-arm64", Label: "arm64", Group: "Windows", InMenu: true, kind: kDocker, image: "windows", script: sWin, env: []string{"ARCHS=arm64"}},
		{Key: "windows", Label: "all", Group: "Windows", InMenu: true, kind: kAggregate,
			members: []string{"windows-x86_64", "windows-arm64"}},

		// ── Publish / validate ──
		{Key: "manifest", Label: "Manifest", Group: "Tools", InMenu: true, kind: kNative, script: "scripts/write_manifest.sh",
			Desc: "write manifest.json + SHA256SUMS for the built libraries"},
		{Key: "verify", Label: "Verify", Group: "Tools", InMenu: true, kind: kDocker, image: "verify", script: "scripts/verify_binaries.sh",
			Desc: "exports, glibc floor, alignment, imports, minimum OS; dlopen"},
		{Key: "sources", Label: "Sources", Group: "Tools", InMenu: true, kind: kNative, script: "scripts/export_sources.sh",
			Desc: "export the patched libsmb2 tree for dart_smb2's ffigen"},

		// ── Non-menu (CLI / internal) ──
		{Key: "docker-image-linux", Label: "Build the Linux build image", Group: "Docker", InMenu: false, kind: kImage, image: "linux"},
		{Key: "docker-image-windows", Label: "Build the Windows build image", Group: "Docker", InMenu: false, kind: kImage, image: "windows"},
		{Key: "docker-image-verify", Label: "Build the Verify image", Group: "Docker", InMenu: false, kind: kImage, image: "verify"},

		// ── Aggregates (CLI convenience) ──
		{Key: "desktop-all", Label: "All desktop targets", Group: "Aggregate", InMenu: false, kind: kAggregate, members: []string{"linux", "windows"}},
		{Key: "all", Label: "Everything + manifest", Group: "Aggregate", InMenu: false, kind: kAggregate,
			members: []string{"macos", "ios", "android", "desktop-all", "manifest"}},
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
