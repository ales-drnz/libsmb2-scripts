// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// ── Update ───────────────────────────────────────────────────────────────────

func (m *model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		return m, nil

	case tickMsg:
		m.spin++
		return m, tick()

	case lineMsg:
		if m.current < len(m.run) {
			it := m.run[m.current]
			it.cnt.add(classify(msg.line))
			it.log = append(it.log, msg.line)
			if len(it.log) > logKeep {
				it.log = it.log[len(it.log)-logKeep:]
			}
		}
		return m, nil

	case doneMsg:
		if m.current >= len(m.run) {
			return m, nil
		}
		it := m.run[m.current]
		it.ended = time.Now()
		if msg.err == nil {
			it.status = stOK
		} else {
			it.status = stFail
		}
		m.current++
		if m.current >= len(m.run) {
			return m, nil
		}
		if msg.err != nil && m.ctx.settings.SkipOnFailure {
			for i := m.current; i < len(m.run); i++ {
				m.run[i].status = stSkipped
			}
			m.current = len(m.run)
			return m, nil
		}
		return m, m.startCurrent()

	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	return m, nil
}

func (m *model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	if key == "ctrl+c" {
		if m.buildActive() {
			m.abortAll()
			return m, nil
		}
		return m, tea.Quit
	}

	// The header tab strip is GLOBAL: once the cursor is up on it (↑ from the
	// top of any section's content) its keys are handled here, whatever the
	// screen underneath.
	if m.onTabs {
		return m.keyHeaderTabs(key)
	}

	switch m.screen {
	case scDash:
		return m.keyDash(key)
	case scLog:
		return m.keyLog(key)
	case scPatches:
		return m.keyPatches(key)
	case scSettings:
		return m.keySettings(key)
	case scDeps:
		return m.keyDeps(key)
	default:
		return m.keySelect(key)
	}
}

// ── Global header tab strip ──────────────────────────────────────────────────
// The Build/Patches/Settings/Dependencies strip is fixed at the top of every
// section. Reached by pressing ↑ at the top of the content; there is a single
// cursor, so when the strip is focused the content shows no selection.

// enterHeaderTabs moves the single cursor up into the top tab strip, starting
// on the current section's tab.
func (m *model) enterHeaderTabs() {
	m.onTabs = true
	m.onAllBin = false
	m.onBuildTabs = false
	m.onBuild = false
	m.tabCur = sectionIndex(m.screen)
}

// dropIntoContent moves the cursor from the strip back down into the current
// section's content (the level just below the header).
func (m *model) dropIntoContent() {
	m.onTabs = false
	if m.screen == scSelect {
		m.onBuildTabs = true // land on the Compile/Tools/Docker sub-tab strip
	}
}

// switchSectionDir navigates to the adjacent section (←→ on the header
// strip), keeping the cursor on the strip so you can keep moving — the
// section underneath switches live.
func (m *model) switchSectionDir(dir int) {
	next := sectionIndex(m.screen) + dir
	if next < 0 || next >= len(topTabs) {
		return // clamp at the ends
	}
	m.screen = screenForTab(next)
	m.enterHeaderTabs()
}

// keyHeaderTabs handles navigation while the cursor is in the top tab strip,
// on any of the top screens. ←→ switches section live; ↓/⏎ drops into the
// section's content.
func (m *model) keyHeaderTabs(key string) (tea.Model, tea.Cmd) {
	switch key {
	case "left", "h":
		m.switchSectionDir(-1)
	case "right", "l":
		m.switchSectionDir(1)
	case "down", "j", "enter", " ", "esc", "q":
		m.dropIntoContent()
	}
	return m, nil
}

// switchSection jumps between the top-level sections (blocked mid-build).
func (m *model) switchSection(key string) (bool, screen) {
	if m.buildActive() {
		return false, m.screen
	}
	switch key {
	case "b":
		return true, scSelect
	case "p":
		return true, scPatches
	case "s":
		return true, scSettings
	case "d":
		return true, scDeps
	}
	return false, m.screen
}
