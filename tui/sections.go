// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

// ── Modular Settings sections ────────────────────────────────────────────────
//
// Everything the user can toggle in Settings is modelled the same way: a
// `section` with a catalog of `toggle`s. libsmb2 has no
// per-feature source toggles (every patch is required correctness or a
// feature dart_smb2 binds), so the only section today is the build knobs —
// but adding a section here is all it takes to grow a new tab of options.

// toggle is a single switchable build option.
type toggle struct {
	Name      string // stable id within its section
	Title     string // short human label
	Desc      string // one-line description
	DefaultOn bool   // part of the curated default set
}

// section is one Settings group.
type section struct {
	Key   string // stable id, namespaces the toggles ("knobs", …)
	Label string
	items func() []toggle
}

// toggleSections is the single registry of Settings sections. Add one here to
// add a group — nothing else to touch.
func toggleSections() []section {
	return []section{
		{Key: "knobs", Label: "Build knobs", items: knobToggles},
	}
}

func knobToggles() []toggle {
	return []toggle{
		{Name: "keepBuild", Title: "Keep build trees", Desc: "do not delete intermediate build directories (KEEP_BUILD=1)"},
		{Name: "forceDownload", Title: "Force re-download", Desc: "redownload the pinned libsmb2 tarball even if cached (FORCE_DOWNLOAD=1)"},
		{Name: "skipOnFailure", Title: "Skip queue on failure", Desc: "on a build failure, mark still-queued targets skipped instead of attempting them"},
	}
}

// knobValue reads one knob's current state from settings.
func knobValue(s userSettings, name string) bool {
	switch name {
	case "keepBuild":
		return s.KeepBuild
	case "forceDownload":
		return s.ForceDownload
	case "skipOnFailure":
		return s.SkipOnFailure
	}
	return false
}

// setKnob writes one knob into settings.
func setKnob(s *userSettings, name string, on bool) {
	switch name {
	case "keepBuild":
		s.KeepBuild = on
	case "forceDownload":
		s.ForceDownload = on
	case "skipOnFailure":
		s.SkipOnFailure = on
	}
}
