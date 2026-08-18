// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "strings"

// viewDeps renders the Dependencies screen: the pinned upstream inputs, read
// live from scripts/shared/_versions.sh.
func (m *model) viewDeps() string {
	var b strings.Builder
	focus := -1
	if m.onTabs {
		focus = m.tabCur
	}
	writeLine(&b, renderHeader(3, focus, m.width, false))

	writeLine(&b, hdrStyle.Render("Pinned upstream"))
	writeLine(&b)
	if len(m.deps) == 0 {
		writeLine(&b, failStyle.Render("  could not parse scripts/shared/_versions.sh"))
	}
	for _, d := range m.deps {
		writeLine(&b, titleStyle.Render("  "+d.Name), dimStyle.Render("  "+d.Version))
		writeLine(&b, dimStyle.Render("    commit  "), textStyle.Render(d.Commit))
		writeLine(&b, dimStyle.Render("    sha256  "), textStyle.Render(d.SHA256))
	}
	writeLine(&b)
	writeLine(&b, dimStyle.Render("Bump: edit scripts/shared/_versions.sh — every patch re-applies"))
	writeLine(&b, dimStyle.Render("against the new tree and fails loudly if an anchor drifted."))

	help := helpBar(
		[2]string{"↑", "sections"},
		[2]string{"b/p/s", "build/patches/settings"},
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
