// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os"
	"path/filepath"
	"regexp"
)

// depInfo describes the pinned upstream inputs of a build, read live from
// scripts/shared/_versions.sh so the Dependencies view can never drift from
// what the build actually fetches.
type depInfo struct {
	Name    string
	Version string // human-readable marker (LIBSMB2_VERSION)
	Commit  string // pinned commit hash
	SHA256  string // tarball checksum
}

var reVersionVar = regexp.MustCompile(`export ([A-Z0-9_]+)="\$\{[A-Z0-9_]+:-([^}]*)\}"`)

// scanDeps parses the _versions.sh defaults (the `${VAR:-default}` values).
func scanDeps(scriptsRoot string) []depInfo {
	data, err := os.ReadFile(filepath.Join(scriptsRoot, "scripts", "shared", "_versions.sh"))
	if err != nil {
		return nil
	}
	vars := map[string]string{}
	for _, mch := range reVersionVar.FindAllStringSubmatch(string(data), -1) {
		vars[mch[1]] = mch[2]
	}
	if vars["LIBSMB2_COMMIT"] == "" {
		return nil
	}
	return []depInfo{{
		Name:    "libsmb2",
		Version: vars["LIBSMB2_VERSION"],
		Commit:  vars["LIBSMB2_COMMIT"],
		SHA256:  vars["LIBSMB2_TARBALL_SHA256"],
	}}
}
