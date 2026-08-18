// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "strings"

// viewSettings renders the Settings screen: every section from
// toggleSections() with live checkbox state, the focused row highlighted.
func (m *model) viewSettings() string {
	var b strings.Builder
	focus := -1
	if m.onTabs {
		focus = m.tabCur
	}
	writeLine(&b, renderHeader(2, focus, m.width, false))

	row := 0
	for _, sec := range toggleSections() {
		writeLine(&b, hdrStyle.Render(sec.Label))
		for _, t := range sec.items() {
			box := boxOff
			on := knobValue(m.ctx.settings, t.Name)
			if on {
				box = boxOn
			}
			if row == m.scursor && !m.onTabs {
				line := "▷ " + box + " " + t.Title + "  — " + t.Desc
				writeLine(&b, hiStyle.Render(padTrunc(line, maxInt(1, m.width-2))))
			} else {
				label := "  " + box + " " + t.Title
				if on {
					writeLine(&b, okStyle.Render(label), dimStyle.Render("  — "+t.Desc))
				} else {
					writeLine(&b, textStyle.Render(label), dimStyle.Render("  — "+t.Desc))
				}
			}
			row++
		}
	}
	writeLine(&b)
	writeLine(&b, dimStyle.Render("Persisted to the user config dir; JOBS=N and friends on the"))
	writeLine(&b, dimStyle.Render("command line still override per invocation."))

	help := helpBar(
		[2]string{"↑↓", "move"},
		[2]string{"space", "toggle"},
		[2]string{"b/p/d", "build/patches/deps"},
		[2]string{"q", "quit"},
	)
	if m.onTabs {
		help = helpBar(
			[2]string{"←→", "switch section"},
			[2]string{"↓", "down"},
			[2]string{"esc", "back"},
		)
	}
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+help)
}

// settingsRows counts the toggle rows across all sections.
func settingsRows() int {
	n := 0
	for _, sec := range toggleSections() {
		n += len(sec.items())
	}
	return n
}

// toggleSettingAt flips the knob at the given flat row index and persists.
func (m *model) toggleSettingAt(row int) {
	i := 0
	for _, sec := range toggleSections() {
		for _, t := range sec.items() {
			if i == row {
				setKnob(&m.ctx.settings, t.Name, !knobValue(m.ctx.settings, t.Name))
				_ = saveSettings(m.ctx.settings)
				return
			}
			i++
		}
	}
}
