// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import (
	"bufio"
	"os/exec"
	"sync"

	tea "github.com/charmbracelet/bubbletea"
)

// runner executes one target's command, streaming lines back into the TUI
// through the program's message loop.
type runner struct {
	mu  sync.Mutex
	cmd *exec.Cmd
}

type lineMsg struct {
	key  string
	line string
}

type doneMsg struct {
	key string
	err error
}

// start launches the target and forwards its combined output as lineMsgs,
// then a doneMsg. It must be used with tea.Program.Send (the goroutine
// outlives the returned Cmd).
func (r *runner) start(p *tea.Program, ctx *buildCtx, t Target) {
	cmd := ctx.command(t)
	// Own process group so abort() can kill the whole tree (bash + compilers
	// + docker). Platform-specific: see procattr_unix.go / procattr_windows.go.
	setProcGroup(cmd)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		p.Send(doneMsg{key: t.Key, err: err})
		return
	}
	cmd.Stderr = cmd.Stdout

	if err := cmd.Start(); err != nil {
		p.Send(doneMsg{key: t.Key, err: err})
		return
	}
	r.mu.Lock()
	r.cmd = cmd
	r.mu.Unlock()

	go func() {
		sc := bufio.NewScanner(stdout)
		sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
		for sc.Scan() {
			p.Send(lineMsg{key: t.Key, line: sc.Text()})
		}
		err := cmd.Wait()
		r.mu.Lock()
		r.cmd = nil
		r.mu.Unlock()
		p.Send(doneMsg{key: t.Key, err: err})
	}()
}

// abort kills the running process group, if any.
func (r *runner) abort() {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.cmd != nil {
		killGroup(r.cmd)
	}
}
