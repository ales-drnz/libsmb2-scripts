// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os/exec"
	"strings"
)

// dockerStatus is a point-in-time snapshot of the build-env image, refreshed
// when the Docker tab is opened or after a build/delete action.
type dockerStatus struct {
	DaemonUp bool
	Exists   bool
	Size     string // human size as reported by docker images
	Created  string // relative creation time
}

// probeDocker inspects the daemon and the libsmb2-builder image.
func probeDocker() dockerStatus {
	var st dockerStatus
	if exec.Command("docker", "info").Run() != nil {
		return st
	}
	st.DaemonUp = true
	out, err := exec.Command("docker", "images", dockerImage,
		"--format", "{{.Size}}\t{{.CreatedSince}}").Output()
	if err != nil {
		return st
	}
	line := strings.TrimSpace(string(out))
	if line == "" {
		return st
	}
	parts := strings.SplitN(line, "\t", 2)
	st.Exists = true
	st.Size = parts[0]
	if len(parts) > 1 {
		st.Created = parts[1]
	}
	return st
}

// deleteDockerImage removes the build-env image (it is rebuilt automatically
// on the next Docker build).
func deleteDockerImage() error {
	return exec.Command("docker", "rmi", dockerImage).Run()
}
