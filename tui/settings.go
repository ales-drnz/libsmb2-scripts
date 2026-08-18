// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// userSettings is the persisted, user-customizable build configuration. It is
// stored as JSON in the user's config dir and is the single source of truth
// for the Settings screen. Environment variables (JOBS=…, KEEP_BUILD=1, …)
// still override per invocation — see buildCtx.knobEnv.
type userSettings struct {
	// Keep intermediate build directories after a build (KEEP_BUILD=1).
	KeepBuild bool `json:"keepBuild"`
	// Redownload the pinned libsmb2 tarball even when cached (FORCE_DOWNLOAD=1).
	ForceDownload bool `json:"forceDownload"`
	// On a build failure, mark every still-queued build as skipped instead of
	// attempting it. Opt-in.
	SkipOnFailure bool `json:"skipOnFailure"`
}

func defaultSettings() userSettings {
	return userSettings{}
}

// settingsPath returns <user-config>/libsmb2-build/settings.json.
func settingsPath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "libsmb2-build", "settings.json"), nil
}

// loadSettings reads the persisted settings, falling back to defaults when
// the file is absent or unreadable.
func loadSettings() userSettings {
	p, err := settingsPath()
	if err != nil {
		return defaultSettings()
	}
	data, err := os.ReadFile(p)
	if err != nil {
		return defaultSettings()
	}
	us := defaultSettings()
	if json.Unmarshal(data, &us) != nil {
		return defaultSettings()
	}
	return us
}

// saveSettings persists the settings, creating the config dir when needed.
func saveSettings(us userSettings) error {
	p, err := settingsPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(us, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(p, data, 0o644)
}
