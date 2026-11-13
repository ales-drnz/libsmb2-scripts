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
	Version string // human-readable marker (LIBSMB2_VERSION, OPENSSL_VERSION)
	Commit  string // pinned commit hash; empty for a release tarball
	Tag     string // release tag of a release tarball (OpenSSL)
	SHA256  string // tarball checksum
}

var reVersionVar = regexp.MustCompile(`export ([A-Z0-9_]+)="\$\{[A-Z0-9_]+:-([^}]*)\}"`)

// versionDefaults parses the `export VAR="${VAR:-default}"` lines of
// _versions.sh: the variables in file order, and the default of each.
func versionDefaults(scriptsRoot string) (names []string, vars map[string]string) {
	vars = map[string]string{}
	data, err := os.ReadFile(filepath.Join(scriptsRoot, "scripts", "shared", "_versions.sh"))
	if err != nil {
		return nil, vars
	}
	for _, mch := range reVersionVar.FindAllStringSubmatch(string(data), -1) {
		names = append(names, mch[1])
		vars[mch[1]] = mch[2]
	}
	return names, vars
}

// scanDeps reads the pins from the _versions.sh defaults.
func scanDeps(scriptsRoot string) []depInfo {
	_, vars := versionDefaults(scriptsRoot)
	if vars["LIBSMB2_COMMIT"] == "" {
		return nil
	}
	deps := []depInfo{{
		Name:    "libsmb2",
		Version: vars["LIBSMB2_VERSION"],
		Commit:  vars["LIBSMB2_COMMIT"],
		SHA256:  vars["LIBSMB2_TARBALL_SHA256"],
	}}
	// libcrypto, built by every platform script and linked into each
	// library.
	if v := vars["OPENSSL_VERSION"]; v != "" {
		deps = append(deps, depInfo{
			Name:    "OpenSSL",
			Version: v,
			Tag:     "openssl-" + v,
			SHA256:  vars["OPENSSL_TARBALL_SHA256"],
		})
	}
	return deps
}
