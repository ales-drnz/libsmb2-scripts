// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"os/exec"
	"strings"
)

// dockerStages are the docker/Dockerfile stages the orchestrator builds, one
// image each.
var dockerStages = []string{"linux", "windows", "verify"}

// imageStatus is one stage image as `docker images` reports it.
type imageStatus struct {
	Stage   string
	Ref     string // libsmb2-build-<stage>:<Dockerfile hash>
	Exists  bool
	Size    string
	Created string
}

// dockerStatus is a point-in-time snapshot of the daemon and the stage
// images, refreshed when the Docker tab is opened or after a build/delete.
type dockerStatus struct {
	DaemonUp bool
	Images   []imageStatus
}

func (s dockerStatus) allBuilt() bool {
	for _, im := range s.Images {
		if !im.Exists {
			return false
		}
	}
	return len(s.Images) > 0
}

// missingKeys are the docker-image-<stage> targets of the images not built.
func (s dockerStatus) missingKeys() []string {
	var keys []string
	for _, im := range s.Images {
		if !im.Exists {
			keys = append(keys, "docker-image-"+im.Stage)
		}
	}
	return keys
}

// probeDocker inspects the daemon and every stage image at the tag the
// current Dockerfile hashes to.
func probeDocker(c *buildCtx) dockerStatus {
	var st dockerStatus
	if exec.Command("docker", "info").Run() != nil {
		return st
	}
	st.DaemonUp = true
	for _, stage := range dockerStages {
		im := imageStatus{Stage: stage, Ref: c.imageRef(stage)}
		out, err := exec.Command("docker", "images", im.Ref,
			"--format", "{{.Size}}\t{{.CreatedSince}}").Output()
		if line := strings.TrimSpace(string(out)); err == nil && line != "" {
			parts := strings.SplitN(line, "\t", 2)
			im.Exists = true
			im.Size = parts[0]
			if len(parts) > 1 {
				im.Created = parts[1]
			}
		}
		st.Images = append(st.Images, im)
	}
	return st
}

// deleteDockerImages removes every tag of the stage images, older
// Dockerfile hashes included. They are rebuilt on the next Docker build.
func deleteDockerImages(c *buildCtx) error {
	var firstErr error
	for _, stage := range dockerStages {
		out, err := exec.Command("docker", "images", "-q", imageRepo(stage)).Output()
		if err != nil {
			continue
		}
		for _, id := range strings.Fields(string(out)) {
			if err := exec.Command("docker", "rmi", "-f", id).Run(); err != nil && firstErr == nil {
				firstErr = err
			}
		}
	}
	return firstErr
}
