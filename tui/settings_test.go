// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "testing"

func TestSettingsRoundTrip(t *testing.T) {
	// Point the user config dir at a temp dir so the test never touches the
	// real settings file.
	t.Setenv("XDG_CONFIG_HOME", t.TempDir())

	if got := loadSettings(); got != defaultSettings() {
		t.Fatalf("fresh loadSettings() = %+v, want defaults", got)
	}

	want := userSettings{KeepBuild: true, ForceDownload: false, SkipOnFailure: true}
	if err := saveSettings(want); err != nil {
		t.Fatal(err)
	}
	if got := loadSettings(); got != want {
		t.Fatalf("loadSettings() after save = %+v, want %+v", got, want)
	}
}

func TestKnobRegistryCoversAllToggles(t *testing.T) {
	// Every toggle in the sections registry must round-trip through
	// setKnob/knobValue — a typo in a Name would silently no-op in the UI.
	var s userSettings
	for _, sec := range toggleSections() {
		for _, tg := range sec.items() {
			setKnob(&s, tg.Name, true)
			if !knobValue(s, tg.Name) {
				t.Errorf("toggle %q does not round-trip through setKnob/knobValue", tg.Name)
			}
			setKnob(&s, tg.Name, false)
		}
	}
}
