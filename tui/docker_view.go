// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "strings"

// renderDockerTab renders the Docker sub-tab body inside the Build selector:
// daemon + build-env image status with build / delete / refresh actions.
func (m *model) renderDockerTab() string {
	m.probeDockerOnce()
	var b strings.Builder

	st := m.docker
	switch {
	case !st.DaemonUp:
		writeLine(&b, failStyle.Render("  ✗ Docker daemon not running"))
		writeLine(&b)
		writeLine(&b, dimStyle.Render("  Start Docker and press r to refresh. Linux and Windows"))
		writeLine(&b, dimStyle.Render("  targets build inside the "+dockerImage+" image."))
	case st.Exists:
		writeLine(&b, okStyle.Render("  ✓ "+dockerImage), dimStyle.Render("   "+st.Size+" · created "+st.Created))
		writeLine(&b)
		writeLine(&b, dimStyle.Render("  One multi-toolchain image: gcc + aarch64 cross for Linux,"))
		writeLine(&b, dimStyle.Render("  MinGW-w64 + LLVM-MinGW for Windows."))
	default:
		writeLine(&b, textStyle.Render("  · "+dockerImage), dimStyle.Render("   not built yet"))
		writeLine(&b)
		writeLine(&b, dimStyle.Render("  Built automatically on the first Linux/Windows build,"))
		writeLine(&b, dimStyle.Render("  or press ⏎ to build it now."))
	}
	return b.String()
}
