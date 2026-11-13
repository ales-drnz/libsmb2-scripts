// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// ── Views ────────────────────────────────────────────────────────────────────

func (m *model) View() string {
	switch m.screen {
	case scDash:
		return m.viewDash()
	case scLog:
		return m.viewLog()
	case scPatches:
		return m.viewPatches()
	case scSettings:
		return m.viewSettings()
	case scDeps:
		return m.viewDeps()
	default:
		return m.viewSelect()
	}
}

// renderBuildTabStrip draws the Compile | Tools | Docker sub-tab row.
func (m *model) renderBuildTabStrip(focused bool) string {
	labels := []string{"Compile", "Tools", "Docker"}
	cells := make([]string, len(labels))
	for i, l := range labels {
		switch {
		case focused && i == m.buildTab:
			cells[i] = tabFocusStyle.Render(l)
		case i == m.buildTab:
			cells[i] = subTabActiveStyle.Render(l)
		default:
			cells[i] = tabInactiveStyle.Render(l)
		}
	}
	return lipgloss.JoinHorizontal(lipgloss.Center, cells...)
}

// gridCellW / gridRowW are the fixed cell geometry shared by the selector and
// the build grid so the two layouts line up exactly.
const (
	gridCellW = 22            // label area inside a cell
	gridRowW  = 2 + gridCellW // leading marker + cell

	// dashRowW is the cell width inside the dashboard's per-OS boxes —
	// narrower than the selector cells so three boxed columns fit an
	// 80-column terminal with their rounded borders + padding.
	dashRowW = 20
)

// renderBandRange renders grid bands [lo,hi) as side-by-side columns.
func (m *model) renderBandRange(cell func(idx int, focused bool) string, cursorInGrid bool, lo, hi int, showHeaders bool) string {
	bands := m.selBands()
	var b strings.Builder
	for bi := lo; bi < hi && bi < len(bands); bi++ {
		band := bands[bi]
		var cols []string
		for ci, c := range band {
			var cb strings.Builder
			if showHeaders {
				writeLine(&cb, hdrStyle.Render(padTrunc(c.group, gridRowW)))
			}
			for ri, idx := range c.items {
				focused := cursorInGrid && m.selBand == bi && m.selCol == ci && m.selRow == ri
				writeLine(&cb, cell(idx, focused))
			}
			cols = append(cols, cb.String())
		}
		writeLine(&b, lipgloss.JoinHorizontal(lipgloss.Top, cols...))
	}
	return b.String()
}

func (m *model) viewSelect() string {
	var b strings.Builder
	focus := -1
	if m.onTabs {
		focus = m.tabCur
	}
	writeLine(&b, renderHeader(0, focus, m.width, false))

	sel := m.selectedCount()

	writeLine(&b, m.renderBuildTabStrip(m.onBuildTabs))
	b.WriteByte('\n')

	cursorInGrid := !m.onBuild && !m.onTabs && !m.onAllBin && !m.onBuildTabs

	okRow := lipgloss.NewStyle().Foreground(cOK)
	row := func(idx int, focused bool) string {
		t := m.menu[idx]
		avail := t.Available()

		// Action cells (run buttons, not checkboxes): the label on the left, a
		// dim one-line description on the right.
		if m.isAction(idx) {
			const actLabelW = 11
			if focused {
				line := "▷ " + padTrunc(t.Label, actLabelW) + t.Desc
				return hiStyle.Render(padTrunc(line, maxInt(1, m.width-2)))
			}
			label, descW := "  "+padTrunc(t.Label, actLabelW), maxInt(1, m.width-actLabelW-4)
			if !avail {
				return dimStyle.Render(label + truncate(t.Desc, descW))
			}
			return lipgloss.NewStyle().Foreground(cAccent2).Render(label) +
				dimStyle.Render(truncate(t.Desc, descW))
		}

		checked := m.cellChecked(idx)
		covered := m.cellCovered(idx)
		check := boxOff
		switch {
		case !avail:
			check = boxNA
		case checked:
			check = boxOn
		}
		var line string
		if focused {
			line = padTrunc("▷ "+check+" "+t.Label, gridRowW)
		} else {
			line = "  " + padTrunc(check+" "+t.Label, gridCellW)
		}
		switch {
		case focused:
			return hiStyle.Render(line)
		case !avail:
			return dimStyle.Render(line)
		case covered:
			return faintStyle.Render(line) // selected but covered → opaque, locked
		case checked:
			return okRow.Render(line)
		default:
			return line
		}
	}

	switch m.buildTab {
	case 0:
		// ── Compile: All binaries + the OS grid + Build button ──
		abCheck := boxOff
		if m.allBinaries {
			abCheck = boxOn
		}
		switch {
		case m.onAllBin:
			writeLine(&b, hiStyle.Render(padTrunc("▷ "+abCheck+" All binaries  — every available target", maxInt(1, m.width-2))))
			b.WriteByte('\n')
		case m.allBinaries:
			writeLine(&b, okStyle.Bold(true).Render("  "+abCheck+" All binaries"), dimStyle.Render("  — every available target"))
			b.WriteByte('\n')
		default:
			writeLine(&b, "  ", abCheck, " All binaries", dimStyle.Render("  — every available target"))
			b.WriteByte('\n')
		}
		b.WriteString(m.renderBandRange(row, cursorInGrid, 0, 2, true))

		label := fmt.Sprintf("Build (%d selected)", sel)
		switch {
		case m.onBuild:
			writeLine(&b, buildBtnFocusStyle.Render(label))
		case sel == 0:
			writeLine(&b, buildBtnDisabledStyle.Render(label))
		default:
			writeLine(&b, buildBtnStyle.Render(label))
		}
	case 1:
		// ── Tools: one-shot actions ──
		b.WriteString(m.renderBandRange(row, cursorInGrid, 2, 3, false))
	default:
		// ── Docker: build-env image management ──
		b.WriteString(m.renderDockerTab())
	}

	b.WriteString("\n")
	if idx, ok := m.focusedIdx(); ok && cursorInGrid && !m.menu[idx].Available() {
		writeLine(&b, warnStyle.Render("⚠ "+m.menu[idx].unavailReason()))
	}
	var help string
	switch {
	case m.onTabs:
		help = helpBar(
			[2]string{"←→", "switch section"},
			[2]string{"↓", "down"},
			[2]string{"esc", "back"},
		)
	case m.onBuildTabs:
		help = helpBar(
			[2]string{"←→", "Compile/Tools/Docker"},
			[2]string{"↓", "into tab"},
			[2]string{"↑", "sections"},
			[2]string{"q", "quit"},
		)
	case m.buildTab == 2:
		act := "build images"
		if m.docker.allBuilt() {
			act = "delete images"
		}
		help = helpBar(
			[2]string{"⏎", act},
			[2]string{"r", "refresh"},
			[2]string{"esc", "tabs"},
			[2]string{"q", "quit"},
		)
	case m.onAllBin:
		help = helpBar(
			[2]string{"space", "toggle all"},
			[2]string{"↓", "targets"},
			[2]string{"↑", "tabs"},
			[2]string{"q", "quit"},
		)
	default:
		space := "toggle"
		if idx, ok := m.focusedIdx(); ok && m.isAction(idx) {
			space = "run"
		}
		help = helpBar(
			[2]string{"↑↓←→", "move"},
			[2]string{"space", space},
			[2]string{"a", "all"},
			[2]string{"⏎", "build"},
			[2]string{"p/s/d", "patches/settings/deps"},
			[2]string{"q", "quit"},
		)
	}
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+help)
}
