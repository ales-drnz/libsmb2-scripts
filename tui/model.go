// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// ── Model ────────────────────────────────────────────────────────────────────

type screen int

const (
	scSelect screen = iota
	scDash
	scLog
	scPatches
	scSettings
	scDeps
)

// sectionIndex maps a screen to its top-tab slot (Build/Patches/Settings/Deps).
func sectionIndex(s screen) int {
	switch s {
	case scPatches:
		return 1
	case scSettings:
		return 2
	case scDeps:
		return 3
	default:
		return 0
	}
}

// screenForTab is sectionIndex's inverse.
func screenForTab(i int) screen {
	switch i {
	case 1:
		return scPatches
	case 2:
		return scSettings
	case 3:
		return scDeps
	default:
		return scSelect
	}
}

type tstatus int

const (
	stQueued tstatus = iota
	stRunning
	stOK
	stFail
	stSkipped
)

// item is one target in the current run: its live status, diagnostics
// counters and captured log.
type item struct {
	t       Target
	status  tstatus
	cnt     counters
	log     []string
	started time.Time
	ended   time.Time
}

const logKeep = 4000 // log lines retained per run item

type model struct {
	ctx     *buildCtx
	program *tea.Program
	runner  *runner

	width, height int
	screen        screen

	// Header tab strip focus
	onTabs bool
	tabCur int

	// Build selector
	menu        []Target
	buildTab    int  // 0 Compile · 1 Tools · 2 Docker
	onBuildTabs bool // cursor on the sub-tab strip
	onAllBin    bool // cursor on the "All binaries" row
	onBuild     bool // cursor on the Build button
	selBand     int
	selCol      int
	selRow      int
	selected    map[string]bool
	allBinaries bool

	// Docker sub-tab
	docker       dockerStatus
	dockerProbed bool

	// Run state
	run     []*item
	current int
	spin    int
	onAbort bool

	// Log screen
	logIdx    int
	logScroll int
	logFollow bool

	// Patches / Settings / Deps
	patches []PatchInfo
	pcursor int
	scursor int
	deps    []depInfo
}

type tickMsg time.Time

func newModel(ctx *buildCtx) *model {
	return &model{
		ctx:      ctx,
		runner:   &runner{},
		menu:     menuTargets(),
		selected: map[string]bool{},
		patches:  scanPatches(ctx.scriptsRoot),
		deps:     scanDeps(ctx.scriptsRoot),
	}
}

func (m *model) Init() tea.Cmd { return tick() }

func tick() tea.Cmd {
	return tea.Tick(120*time.Millisecond, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func (m *model) buildActive() bool {
	for _, it := range m.run {
		if it.status == stQueued || it.status == stRunning {
			return true
		}
	}
	return false
}
