// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "strings"

// renderDockerTab renders the Docker sub-tab body inside the Build selector:
// daemon and stage image status, with build / delete / refresh actions.
func (m *model) renderDockerTab() string {
	m.probeDockerOnce()
	var b strings.Builder

	st := m.docker
	if !st.DaemonUp {
		writeLine(&b, failStyle.Render("  ✗ Docker daemon not running"))
		writeLine(&b)
		writeLine(&b, dimStyle.Render("  Start Docker and press r to refresh. Linux, Windows and"))
		writeLine(&b, dimStyle.Render("  Verify run inside the docker/Dockerfile stage images."))
		return b.String()
	}
	for _, im := range st.Images {
		if im.Exists {
			writeLine(&b, okStyle.Render("  ✓ "+im.Ref), dimStyle.Render("   "+im.Size+" · created "+im.Created))
		} else {
			writeLine(&b, textStyle.Render("  · "+im.Ref), dimStyle.Render("   not built yet"))
		}
	}
	writeLine(&b)
	if st.allBuilt() {
		writeLine(&b, dimStyle.Render("  linux: ubuntu 20.04 gcc (glibc 2.31) · windows: llvm-mingw"))
		writeLine(&b, dimStyle.Render("  verify: binutils + LLVM. ⏎ deletes them, r refreshes."))
	} else {
		writeLine(&b, dimStyle.Render("  Built automatically before the first build that needs one,"))
		writeLine(&b, dimStyle.Render("  or press ⏎ to build the missing ones now."))
	}
	return b.String()
}
