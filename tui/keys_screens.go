// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	tea "github.com/charmbracelet/bubbletea"
)

func (m *model) keyDash(key string) (tea.Model, tea.Cmd) {
	active := m.buildActive()
	switch key {
	case "q":
		if active {
			m.abortAll()
			return m, nil
		}
		return m, tea.Quit
	case "c":
		if active {
			m.abortAll()
		}
		return m, nil
	case "esc":
		if !active {
			m.screen = scSelect
		}
		return m, nil
	case "up", "k":
		m.logIdx = clampInt(m.logIdx-1, 0, len(m.run)-1)
	case "down", "j":
		if m.onAbort {
			return m, nil
		}
		m.logIdx = clampInt(m.logIdx+1, 0, len(m.run)-1)
	case "tab":
		if active {
			m.onAbort = !m.onAbort
		}
	case "enter", " ":
		if m.onAbort && active {
			m.abortAll()
			m.onAbort = false
			return m, nil
		}
		m.openLog(m.logIdx)
	}
	return m, nil
}

func (m *model) keyLog(key string) (tea.Model, tea.Cmd) {
	it := m.run[m.logIdx]
	page := maxInt(1, m.logWindowHeight())
	switch key {
	case "esc", "enter":
		m.screen = scDash
	case "up", "k":
		m.logFollow = false
		m.logScroll = clampInt(m.logScroll-1, 0, m.maxScroll(it))
	case "down", "j":
		m.logScroll = clampInt(m.logScroll+1, 0, m.maxScroll(it))
	case "pgup":
		m.logFollow = false
		m.logScroll = clampInt(m.logScroll-page, 0, m.maxScroll(it))
	case "pgdown":
		m.logScroll = clampInt(m.logScroll+page, 0, m.maxScroll(it))
	case "g":
		m.logFollow = false
		m.logScroll = 0
	case "G", "f":
		m.logFollow = true
	case "q":
		if m.buildActive() {
			m.abortAll()
			return m, nil
		}
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keyPatches(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		return m, nil
	}
	switch key {
	case "up", "k":
		if m.pcursor == 0 {
			m.enterHeaderTabs()
		} else {
			m.pcursor--
		}
	case "down", "j":
		m.pcursor = clampInt(m.pcursor+1, 0, len(m.patches)-1)
	case "esc":
		m.enterHeaderTabs()
	case "q":
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keySettings(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		return m, nil
	}
	switch key {
	case "up", "k":
		if m.scursor == 0 {
			m.enterHeaderTabs()
		} else {
			m.scursor--
		}
	case "down", "j":
		m.scursor = clampInt(m.scursor+1, 0, settingsRows()-1)
	case " ", "enter":
		m.toggleSettingAt(m.scursor)
	case "esc":
		m.enterHeaderTabs()
	case "q":
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keyDeps(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		return m, nil
	}
	switch key {
	case "up", "k", "esc":
		m.enterHeaderTabs()
	case "q":
		return m, tea.Quit
	}
	return m, nil
}
