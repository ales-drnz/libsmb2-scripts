// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"strings"
)

// ── Log screen ───────────────────────────────────────────────────────────────

func (m *model) logWindowHeight() int {
	return maxInt(4, m.height-6)
}

func (m *model) maxScroll(it *item) int {
	return maxInt(0, len(it.log)-m.logWindowHeight())
}

func (m *model) openLog(ri int) {
	if ri < 0 || ri >= len(m.run) {
		return
	}
	m.screen = scLog
	m.logIdx = ri
	m.logFollow = true
	m.logScroll = m.maxScroll(m.run[ri])
}

func (m *model) viewLog() string {
	it := m.run[m.logIdx]
	var b strings.Builder
	writeLine(&b, renderHeader(0, -1, m.width, m.buildActive()))

	glyph, gstyle := m.glyphFor(it.status)
	writeLine(&b,
		gstyle.Render(glyph+" "+it.t.fullLabel()),
		dimStyle.Render("   "+statusWord(it.status)+"   "+m.timeCell(it)+"   "),
		counterBar(it.cnt.info, it.cnt.warn, it.cnt.errs),
	)
	b.WriteByte('\n')

	if m.logFollow {
		m.logScroll = m.maxScroll(it)
	}
	h := m.logWindowHeight()
	lines := make([]string, len(it.log))
	for i, l := range it.log {
		lines[i] = logStyle.Render(truncate(l, maxInt(8, m.width-4)))
	}
	b.WriteString(scrollView(lines, h, m.logScroll))

	follow := "follow"
	if m.logFollow {
		follow = "following"
	}
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+helpBar(
		[2]string{"↑↓", "scroll"},
		[2]string{"g/G", "top/bottom"},
		[2]string{"f", follow},
		[2]string{"esc", "back"},
		[2]string{"q", "quit"},
	))
}
