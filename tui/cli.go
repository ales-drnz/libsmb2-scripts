// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"fmt"
	"os"
)

// runCLI runs targets headlessly (no TUI), streaming output straight to the
// terminal. Stops at the first failure, like `make`.
//
//	./build linux windows
//	./build macos verify
//	./build all
func runCLI(args []string, ctx *buildCtx) int {
	keys := args
	if keys[0] == "build" {
		keys = keys[1:]
	}
	if len(keys) == 0 {
		printUsage()
		return 1
	}
	targets, skipped, err := ctx.expand(keys)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	for _, s := range skipped {
		fmt.Printf("\x1b[2m- skip %s\x1b[0m\n", s)
	}
	for _, t := range targets {
		fmt.Printf("\n\x1b[1;36m▶ %s\x1b[0m\n", t.fullLabel())
		cmd := ctx.command(t)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.Stdin = os.Stdin
		if err := cmd.Run(); err != nil {
			fmt.Fprintf(os.Stderr, "\x1b[1;31m✗ %s failed: %v\x1b[0m\n", t.Key, err)
			return 1
		}
		fmt.Printf("\x1b[1;32m✓ %s\x1b[0m\n", t.Key)
	}
	return 0
}

func printUsage() {
	fmt.Print(`libsmb2 build orchestrator

USAGE
  ./build                  interactive dashboard (default)
  ./build <target...>      build the given targets, headless
  ./build list             list all targets
  ./build patches          list the patch set applied to upstream libsmb2
  ./build help             this help

EXAMPLES
  ./build                          # open the dashboard
  ./build linux windows            # desktop builds (Docker)
  ./build macos verify             # build macOS, then verify everything built
  ./build all                      # everything this host can build; the manifest
                                   # too when nothing had to be skipped

KNOBS (env, forwarded into Docker builds)
  JOBS=N  KEEP_BUILD=1  FORCE_DOWNLOAD=1

Outputs land in release_builds/. Apple targets require macOS; Linux, Windows
and Verify run in Docker; Android needs the pinned NDK on the host. CI
(.github/workflows/build.yml) builds all nine on GitHub's runners.
`)
}

func printList() {
	group := ""
	for _, t := range allTargets() {
		if t.Group != group {
			fmt.Printf("\n%s\n", t.Group)
			group = t.Group
		}
		avail := ""
		if !t.Available() {
			avail = "  (" + t.unavailReason() + ")"
		}
		fmt.Printf("  %-20s %s%s\n", t.Key, t.Label, avail)
	}
	fmt.Println()
}

func printPatches(ctx *buildCtx) {
	patches := scanPatches(ctx.scriptsRoot)
	if len(patches) == 0 {
		fmt.Println("no patches found under patches/libsmb2/")
		return
	}
	scope := ""
	for _, p := range patches {
		if p.Scope != scope {
			fmt.Printf("\n%s\n", p.Scope)
			scope = p.Scope
		}
		fmt.Printf("  %-32s %s\n", p.Name, p.Title)
	}
	fmt.Println()
}
