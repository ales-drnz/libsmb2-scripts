// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

func writeParts(b *strings.Builder, parts ...string) {
	for _, part := range parts {
		b.WriteString(part)
	}
}

func writeLine(b *strings.Builder, parts ...string) {
	writeParts(b, parts...)
	b.WriteByte('\n')
}

// anchorBottom pins `footer` to the bottom rows of the terminal by padding
// the gap between it and `body` with blank lines, so the help bar keeps its
// position no matter how tall the content above it is. When the body is
// TALLER than the space available it is cropped from the bottom instead —
// the header must stay fixed at the top; overflowing would scroll it away.
func (m *model) anchorBottom(body, footer string) string {
	body = strings.TrimRight(body, "\n")
	// bottomMargin keeps the help bar off the very last terminal row,
	// mirroring the breathing room it has above (the rule + gap), so it
	// doesn't read as glued to the bottom edge.
	const bottomMargin = 1
	if m.height > 0 {
		maxBody := m.height - lipgloss.Height(footer) - bottomMargin
		if lines := strings.Split(body, "\n"); len(lines) > maxBody && maxBody > 0 {
			body = strings.Join(lines[:maxBody], "\n")
		}
	}
	pad := m.height - lipgloss.Height(body) - lipgloss.Height(footer) - bottomMargin + 1
	if pad < 1 {
		pad = 1
	}
	return body + strings.Repeat("\n", pad) + footer + strings.Repeat("\n", bottomMargin)
}
