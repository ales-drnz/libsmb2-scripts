// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// renderDashBoxes lays out the dashboard grid with each OS group wrapped in a
// rounded box — the OS name as the box title, its per-arch rows inside, the
// border tinted by the group's combined run status: running (blue), done
// (green), failed (red); groups not part of the run keep a faint idle border.
func (m *model) renderDashBoxes(cell func(idx int) string) string {
	bands := m.selBands()
	var b strings.Builder
	for bi := 0; bi < 2 && bi < len(bands); bi++ {
		var cols []string
		for _, c := range bands[bi] {
			borderColor := cBorder
			titleSt := faintStyle
			var items []*item
			for _, idx := range c.items {
				items = append(items, m.cellRunItems(idx)...)
			}
			if len(items) > 0 {
				switch combinedStatus(items) {
				case stRunning:
					borderColor, titleSt = cRun, runStyle
				case stOK:
					borderColor, titleSt = cOK, okStyle
				case stFail:
					borderColor, titleSt = cFail, failStyle
				}
			}
			var cb strings.Builder
			writeLine(&cb, titleSt.Bold(true).Render(padTrunc(c.group, dashRowW)))
			for _, idx := range c.items {
				writeLine(&cb, cell(idx))
			}
			box := lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(borderColor).
				Padding(0, 1).
				Render(strings.TrimRight(cb.String(), "\n"))
			cols = append(cols, box)
		}
		writeLine(&b, lipgloss.JoinHorizontal(lipgloss.Top, cols...))
	}
	return b.String()
}

func (m *model) viewDash() string {
	var b strings.Builder
	locked := m.buildActive()
	writeLine(&b, renderHeader(0, -1, m.width, locked))

	// progress summary: bar + done count + total ℹ/⚠/✗ across all builds
	done, total := m.progress()
	var ti, tw, te int
	for _, it := range m.run {
		ti += it.cnt.info
		tw += it.cnt.warn
		te += it.cnt.errs
	}
	bar := progressBar(done, total, clampInt(m.width/3, 8, 40))
	writeLine(&b,
		bar,
		"  ",
		dimStyle.Render(fmt.Sprintf("%d/%d done", done, total)),
		dimStyle.Render("   "),
		counterBar(ti, tw, te),
	)

	// aux run items that have no grid cell (the docker-image prep step)
	if aux := m.auxItems(); len(aux) > 0 {
		b.WriteString("\n")
		for _, it := range aux {
			glyph, gstyle := m.glyphFor(it.status)
			label := "build-env image"
			if it.status == stRunning {
				if cur := lastLogLine(it); cur != "" {
					label += "  ·  " + cur
				}
			}
			text := label + "  " + m.timeCell(it)
			writeLine(&b, gstyle.Render(glyph), " ", dimStyle.Render(truncate(text, maxInt(8, m.width-2))))
		}
	}
	b.WriteString("\n")

	// the grid, run-mode cells
	cell := func(idx int) string {
		t := m.menu[idx]
		items := m.cellRunItems(idx)
		inRun := len(items) > 0
		glyph, gstyle := "·", faintStyle
		if inRun {
			glyph, gstyle = m.glyphFor(combinedStatus(items))
		}
		ls := faintStyle
		if inRun {
			ls = textStyle
		}
		return gstyle.Render(glyph) + " " + ls.Render(padTrunc(t.Label, dashRowW-2))
	}
	b.WriteString(m.renderDashBoxes(cell))

	// focused run item readout + selector
	b.WriteString("\n")
	for i, it := range m.run {
		glyph, gstyle := m.glyphFor(it.status)
		line := gstyle.Render(glyph+" "+it.t.fullLabel()) +
			dimStyle.Render("    "+statusWord(it.status)) +
			dimStyle.Render("    "+m.timeCell(it)) +
			dimStyle.Render("    ") + counterBar(it.cnt.info, it.cnt.warn, it.cnt.errs)
		if i == m.logIdx && !m.onAbort {
			line = hiStyle.Render("▷ ") + line
		} else {
			line = "  " + line
		}
		writeLine(&b, truncate(line, maxInt(20, m.width)))
	}

	// Red Abort button — cancels the running + queued builds.
	if m.buildActive() {
		label := "✕ Abort all builds"
		b.WriteByte('\n')
		if m.onAbort {
			writeLine(&b, abortBtnFocusStyle.Render(label))
		} else {
			writeLine(&b, abortBtnStyle.Render(label))
		}
	}

	enterHint := [2]string{"⏎", "view log"}
	if m.onAbort {
		enterHint = [2]string{"⏎", "abort all"}
	}
	pairs := [][2]string{
		{"↑↓", "move"},
		enterHint,
	}
	if m.buildActive() {
		pairs = append(pairs, [2]string{"tab", "abort btn"}, [2]string{"c", "cancel"})
	} else {
		pairs = append(pairs, [2]string{"esc", "back"})
	}
	pairs = append(pairs, [2]string{"q", "quit"})
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+helpBar(pairs...))
}

// lastLogLine returns the most recent non-empty line of an item's captured
// output (used to surface a docker build's current step live).
func lastLogLine(it *item) string {
	for i := len(it.log) - 1; i >= 0; i-- {
		if s := strings.TrimSpace(it.log[i]); s != "" {
			return s
		}
	}
	return ""
}
