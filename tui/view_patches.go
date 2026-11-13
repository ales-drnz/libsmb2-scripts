// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"fmt"
	"strings"
)

// ── Patches screen ───────────────────────────────────────────────────────────

func (m *model) viewPatches() string {
	var b strings.Builder
	focus := -1
	if m.onTabs {
		focus = m.tabCur
	}
	writeLine(&b, renderHeader(1, focus, m.width, false))

	if len(m.patches) == 0 {
		writeLine(&b, dimStyle.Render("no patches found under patches/libsmb2/"))
		return m.anchorBottom(b.String(), hrule(m.width)+"\n"+helpBar([2]string{"b", "build"}, [2]string{"q", "quit"}))
	}
	scope := ""
	listRows := 0
	for i, p := range m.patches {
		if p.Scope != scope {
			scope = p.Scope
			writeLine(&b, hdrStyle.Render(scope))
			listRows++
		}
		line := fmt.Sprintf("  %-32s %s", p.Name, truncate(p.Title, maxInt(8, m.width-38)))
		if i == m.pcursor && !m.onTabs {
			writeLine(&b, hiStyle.Render(padTrunc("▷"+line[1:], maxInt(1, m.width-2))))
		} else {
			writeLine(&b, textStyle.Render(line))
		}
		listRows++
	}
	writeLine(&b)

	// Detail panel for the focused patch, WINDOWED to the space left below the
	// list: the whole screen must never exceed the terminal height, or the
	// fixed header scrolls out of view.
	p := m.patches[m.pcursor]
	width := maxInt(20, m.width-4)
	inner := maxInt(10, width-2) // inside the panel borders/padding
	lines := []string{titleStyle.Render(truncate(p.Title, inner))}
	if p.Body != "" {
		lines = append(lines, "")
		for _, l := range strings.Split(p.Body, "\n") {
			lines = append(lines, logStyle.Render(truncate(l, inner)))
		}
	}
	if m.height > 0 {
		// header(2) + list + blank + panel borders(2) + rule + help + margin(2)
		avail := m.height - 2 - listRows - 1 - 2 - 2 - 2
		if avail < 3 {
			avail = 3
		}
		if len(lines) > avail {
			lines = append(lines[:avail-1], dimStyle.Render("… ↑↓ another patch, or widen the terminal"))
		}
	}
	writeLine(&b, panelStyle.Width(width).Render(strings.Join(lines, "\n")))

	help := helpBar(
		[2]string{"↑↓", "browse"},
		[2]string{"b/s/d", "build/settings/deps"},
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
