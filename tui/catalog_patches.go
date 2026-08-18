// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// PatchInfo is one patch_*.py from patches/libsmb2/<scope>/, described by the
// first line of its module docstring. The catalog is read from disk so the
// Patches tab can never drift from what the build actually applies.
type PatchInfo struct {
	Scope string // "shared" | "windows" | ...
	Name  string // file basename
	Title string // first docstring line
	Body  string // remaining docstring lines
}

func scanPatches(scriptsRoot string) []PatchInfo {
	var out []PatchInfo
	base := filepath.Join(scriptsRoot, "patches", "libsmb2")
	scopes, err := os.ReadDir(base)
	if err != nil {
		return nil
	}
	for _, sc := range scopes {
		if !sc.IsDir() {
			continue
		}
		files, err := os.ReadDir(filepath.Join(base, sc.Name()))
		if err != nil {
			continue
		}
		for _, f := range files {
			name := f.Name()
			if !strings.HasPrefix(name, "patch_") || !strings.HasSuffix(name, ".py") {
				continue
			}
			title, body := readDocstring(filepath.Join(base, sc.Name(), name))
			out = append(out, PatchInfo{Scope: sc.Name(), Name: name, Title: title, Body: body})
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Scope != out[j].Scope {
			return out[i].Scope < out[j].Scope
		}
		return out[i].Name < out[j].Name
	})
	return out
}

// readDocstring extracts a Python module's triple-quoted docstring, split
// into its first line (title) and the rest (body).
func readDocstring(path string) (string, string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", ""
	}
	s := string(data)
	start := strings.Index(s, `"""`)
	if start < 0 {
		return "", ""
	}
	rest := s[start+3:]
	end := strings.Index(rest, `"""`)
	if end < 0 {
		return "", ""
	}
	doc := strings.TrimSpace(rest[:end])
	if i := strings.IndexByte(doc, '\n'); i >= 0 {
		return strings.TrimSpace(doc[:i]), strings.TrimSpace(doc[i+1:])
	}
	return doc, ""
}
