// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

// libsmb2 build orchestrator — interactive dashboard + headless CLI.
//
// The interactive mode is a Bubble Tea app with the same screens as the
// sibling orchestrators: a Build selector (target grid + sub-tabs), a live
// build dashboard, a full-screen log viewer, and Patches / Settings /
// Dependencies sections. The headless mode (./build <target...>) streams
// straight to the terminal.
package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	ctx, err := newBuildCtx()
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}

	args := os.Args[1:]
	if len(args) > 0 {
		switch args[0] {
		case "help", "-h", "--help":
			printUsage()
			return
		case "list":
			printList()
			return
		case "patches":
			printPatches(ctx)
			return
		default:
			os.Exit(runCLI(args, ctx))
		}
	}

	m := newModel(ctx)
	p := tea.NewProgram(m, tea.WithAltScreen())
	m.program = p
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
