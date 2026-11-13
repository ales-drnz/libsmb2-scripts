// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	tea "github.com/charmbracelet/bubbletea"
)

func (m *model) keySelect(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		m.onTabs = false
		return m, nil
	}

	bands := m.selBands()
	lo, hi := m.gridBandRange()

	// Sub-tab strip (Compile | Tools | Docker)
	if m.onBuildTabs {
		switch key {
		case "left", "h":
			m.buildTab = clampInt(m.buildTab-1, 0, 2)
		case "right", "l":
			m.buildTab = clampInt(m.buildTab+1, 0, 2)
		case "up", "k":
			m.enterHeaderTabs()
		case "down", "j", "enter", " ":
			m.onBuildTabs = false
			switch m.buildTab {
			case 0:
				m.onAllBin = true
			case 1:
				m.selBand, m.selCol, m.selRow = 2, 0, 0
			case 2:
				m.probeDockerOnce()
			}
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// "All binaries" master row
	if m.onAllBin {
		switch key {
		case " ":
			m.allBinaries = !m.allBinaries
		case "up", "k":
			m.onAllBin = false
			m.onBuildTabs = true
		case "down", "j":
			m.onAllBin = false
			m.selBand, m.selCol, m.selRow = lo, 0, 0
		case "enter":
			return m, m.startBuild()
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// Build button
	if m.onBuild {
		switch key {
		case "enter", " ":
			return m, m.startBuild()
		case "up", "k":
			m.onBuild = false
			m.selBand = hi - 1
			m.selCol, m.selRow = 0, 0
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// Docker sub-tab body
	if m.buildTab == 2 {
		switch key {
		case "up", "k", "esc":
			m.onBuildTabs = true
		case "enter", " ":
			if m.docker.allBuilt() {
				_ = deleteDockerImages(m.ctx)
				m.docker = probeDocker(m.ctx)
			} else {
				return m, m.startKeys(m.docker.missingKeys())
			}
		case "r":
			m.docker = probeDocker(m.ctx)
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// Grid navigation
	clampRow := func() {
		col := bands[m.selBand][m.selCol]
		m.selRow = clampInt(m.selRow, 0, len(col.items)-1)
	}
	switch key {
	case "up", "k":
		if m.selRow > 0 {
			m.selRow--
		} else if m.selBand > lo {
			m.selBand--
			m.selCol = clampInt(m.selCol, 0, len(bands[m.selBand])-1)
			m.selRow = len(bands[m.selBand][m.selCol].items) - 1
		} else if m.buildTab == 0 {
			m.onAllBin = true
		} else {
			m.onBuildTabs = true
		}
	case "down", "j":
		col := bands[m.selBand][m.selCol]
		if m.selRow < len(col.items)-1 {
			m.selRow++
		} else if m.selBand < hi-1 {
			m.selBand++
			m.selCol = clampInt(m.selCol, 0, len(bands[m.selBand])-1)
			m.selRow = 0
		} else {
			m.onBuild = true
		}
	case "left", "h":
		if m.selCol > 0 {
			m.selCol--
			clampRow()
		}
	case "right", "l":
		if m.selCol < len(bands[m.selBand])-1 {
			m.selCol++
			clampRow()
		}
	case " ":
		if idx, ok := m.focusedIdx(); ok {
			t := m.menu[idx]
			if m.isAction(idx) {
				return m, m.startKeys([]string{t.Key})
			}
			if t.Available() && !m.cellCovered(idx) {
				m.selected[t.Key] = !m.selected[t.Key]
			}
		}
	case "a":
		m.allBinaries = !m.allBinaries
	case "enter":
		return m, m.startBuild()
	case "esc":
		m.onBuildTabs = true
	case "q":
		return m, tea.Quit
	}
	return m, nil
}
