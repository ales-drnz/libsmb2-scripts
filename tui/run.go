// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// ── Run orchestration ────────────────────────────────────────────────────────

func (m *model) startBuild() tea.Cmd {
	return m.startKeys(m.selectionKeys())
}

func (m *model) startKeys(keys []string) tea.Cmd {
	if len(keys) == 0 {
		return nil
	}
	queue, _, err := m.ctx.expand(keys)
	if err != nil || len(queue) == 0 {
		return nil
	}
	m.run = nil
	for _, t := range queue {
		m.run = append(m.run, &item{t: t})
	}
	m.current = 0
	m.logIdx = 0
	m.onAbort = false
	m.screen = scDash
	return m.startCurrent()
}

func (m *model) startCurrent() tea.Cmd {
	it := m.run[m.current]
	it.status = stRunning
	it.started = time.Now()
	go m.runner.start(m.program, m.ctx, it.t)
	return nil
}

func (m *model) abortAll() {
	m.runner.abort()
	for i := m.current + 1; i < len(m.run); i++ {
		m.run[i].status = stSkipped
	}
}

func (m *model) probeDockerOnce() {
	if !m.dockerProbed {
		m.docker = probeDocker(m.ctx)
		m.dockerProbed = true
	}
}

func (m *model) progress() (done, total int) {
	for _, it := range m.run {
		if it.status == stOK || it.status == stFail || it.status == stSkipped {
			done++
		}
	}
	return done, len(m.run)
}

// cellRunItems returns the run items a grid cell represents: its own key, or
// its members when it is a group "all" aggregate.
func (m *model) cellRunItems(idx int) []*item {
	t := m.menu[idx]
	keys := map[string]bool{t.Key: true}
	if full, ok := targetByKey(t.Key); ok {
		for _, mk := range full.members {
			keys[mk] = true
			if mt, ok2 := targetByKey(mk); ok2 {
				for _, mk2 := range mt.members {
					keys[mk2] = true
				}
			}
		}
	}
	var out []*item
	for _, it := range m.run {
		if keys[it.t.Key] {
			out = append(out, it)
		}
	}
	return out
}

// auxItems are run items with no grid cell (the docker-image prep step).
func (m *model) auxItems() []*item {
	var out []*item
	for _, it := range m.run {
		if it.t.kind == kImage {
			out = append(out, it)
		}
	}
	return out
}

func combinedStatus(items []*item) tstatus {
	st := stOK
	sawQueued := false
	for _, it := range items {
		switch it.status {
		case stRunning:
			return stRunning
		case stFail:
			st = stFail
		case stQueued, stSkipped:
			sawQueued = true
		}
	}
	if sawQueued && st == stOK {
		return stQueued
	}
	return st
}

func (m *model) glyphFor(st tstatus) (string, lipgloss.Style) {
	switch st {
	case stRunning:
		return spinnerFrames[m.spin%len(spinnerFrames)], runStyle
	case stOK:
		return "✓", okStyle
	case stFail:
		return "✗", failStyle
	case stSkipped:
		return "–", faintStyle
	default:
		return "·", dimStyle
	}
}

func statusWord(st tstatus) string {
	switch st {
	case stRunning:
		return "building"
	case stOK:
		return "done"
	case stFail:
		return "failed"
	case stSkipped:
		return "skipped"
	default:
		return "queued"
	}
}

func (m *model) timeCell(it *item) string {
	switch it.status {
	case stRunning:
		return time.Since(it.started).Round(time.Second).String()
	case stOK, stFail:
		return it.ended.Sub(it.started).Round(time.Second).String()
	}
	return ""
}
