// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

// ── Selector grid geometry ───────────────────────────────────────────────────

type selColumn struct {
	group string
	items []int
}

// selBands lays the OS sections out as bands of side-by-side columns:
//
//	band 0: macOS · iOS
//	band 1: Windows · Linux · Android
//	band 2: Tools
func (m *model) selBands() [][]selColumn {
	col := func(g string) selColumn {
		var idx []int
		for i, t := range m.menu {
			if t.Group == g {
				idx = append(idx, i)
			}
		}
		return selColumn{g, idx}
	}
	return [][]selColumn{
		{col("macOS"), col("iOS")},
		{col("Windows"), col("Linux"), col("Android")},
		{col("Tools")},
	}
}

// gridBandRange returns the [lo, hi) band indices shown by the active build
// sub-tab: Compile shows the OS bands, Tools shows the actions band.
func (m *model) gridBandRange() (int, int) {
	if m.buildTab == 1 {
		return 2, 3
	}
	return 0, 2
}

// focusedIdx returns the menu index under the grid cursor.
func (m *model) focusedIdx() (int, bool) {
	bands := m.selBands()
	if m.selBand >= len(bands) {
		return 0, false
	}
	band := bands[m.selBand]
	if m.selCol >= len(band) {
		return 0, false
	}
	col := band[m.selCol]
	if m.selRow >= len(col.items) {
		return 0, false
	}
	return col.items[m.selRow], true
}

// isAction reports whether a menu index is a Tools run-button (not a checkbox).
func (m *model) isAction(idx int) bool { return m.menu[idx].Group == "Tools" }

// ── Hierarchical selection ───────────────────────────────────────────────────
//
// A group's "all" cell (Linux all, Android all, …) covers that group's
// per-arch cells; "All binaries" covers every cell. A covered cell shows
// checked but dimmed and can't be toggled.

// groupAllKey returns the key of a group's "all" target, or "".
func groupAllKey(group string) string {
	switch group {
	case "Android":
		return "android"
	case "Linux":
		return "linux"
	case "Windows":
		return "windows"
	}
	return ""
}

// groupPrimaryKey is the one target key that represents a whole group when
// "All binaries" is on.
func groupPrimaryKey(group string) string {
	switch group {
	case "macOS":
		return "macos"
	case "iOS":
		return "ios"
	}
	return groupAllKey(group)
}

func (m *model) cellCovered(idx int) bool {
	t := m.menu[idx]
	if !t.Available() || m.isAction(idx) {
		return false
	}
	if m.allBinaries {
		return true
	}
	if ga := groupAllKey(t.Group); ga != "" && ga != t.Key && m.selected[ga] {
		return true
	}
	return false
}

func (m *model) cellChecked(idx int) bool {
	return m.selected[m.menu[idx].Key] || m.cellCovered(idx)
}

// selectionKeys resolves the hierarchy into the concrete target keys to build.
func (m *model) selectionKeys() []string {
	if m.allBinaries {
		var keys []string
		seen := map[string]bool{}
		for _, t := range m.menu {
			if m.isAction(0) && t.Group == "Tools" {
				continue
			}
			k := groupPrimaryKey(t.Group)
			if k == "" || seen[k] {
				continue
			}
			if pt, ok := targetByKey(k); !ok || !pt.Available() {
				continue
			}
			seen[k] = true
			keys = append(keys, k)
		}
		return keys
	}
	var keys []string
	for i, t := range m.menu {
		if m.isAction(i) || !m.selected[t.Key] || m.cellCovered(i) {
			continue
		}
		keys = append(keys, t.Key)
	}
	return keys
}

func (m *model) selectedCount() int { return len(m.selectionKeys()) }
