// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

// libsmb2 build orchestrator — interactive dashboard + headless CLI.
//
// The interactive mode is a Bubble Tea app with the same screens as the
// sibling orchestrators: a Build selector (target grid + sub-tabs), a live
// build dashboard, a full-screen log viewer, and Patches / Settings /
// Dependencies sections. The headless mode (./build <target...>) streams
// straight to the terminal.
package main

import (
	"fmt"
	"os"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func main() {
	ctx, err := newBuildCtx()
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}

	args := os.Args[1:]
	if len(args) > 0 {
		switch args[0] {
		case "help", "-h", "--help":
			printUsage()
			return
		case "list":
			printList()
			return
		case "patches":
			printPatches(ctx)
			return
		default:
			os.Exit(runCLI(args, ctx))
		}
	}

	m := newModel(ctx)
	p := tea.NewProgram(m, tea.WithAltScreen())
	m.program = p
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

// ── Model ────────────────────────────────────────────────────────────────────

type screen int

const (
	scSelect screen = iota
	scDash
	scLog
	scPatches
	scSettings
	scDeps
)

// sectionIndex maps a screen to its top-tab slot (Build/Patches/Settings/Deps).
func sectionIndex(s screen) int {
	switch s {
	case scPatches:
		return 1
	case scSettings:
		return 2
	case scDeps:
		return 3
	default:
		return 0
	}
}

// screenForTab is sectionIndex's inverse.
func screenForTab(i int) screen {
	switch i {
	case 1:
		return scPatches
	case 2:
		return scSettings
	case 3:
		return scDeps
	default:
		return scSelect
	}
}

type tstatus int

const (
	stQueued tstatus = iota
	stRunning
	stOK
	stFail
	stSkipped
)

// item is one target in the current run: its live status, diagnostics
// counters and captured log.
type item struct {
	t       Target
	status  tstatus
	cnt     counters
	log     []string
	started time.Time
	ended   time.Time
}

const logKeep = 4000 // log lines retained per run item

type model struct {
	ctx     *buildCtx
	program *tea.Program
	runner  *runner

	width, height int
	screen        screen

	// Header tab strip focus
	onTabs bool
	tabCur int

	// Build selector
	menu        []Target
	buildTab    int  // 0 Compile · 1 Tools · 2 Docker
	onBuildTabs bool // cursor on the sub-tab strip
	onAllBin    bool // cursor on the "All binaries" row
	onBuild     bool // cursor on the Build button
	selBand     int
	selCol      int
	selRow      int
	selected    map[string]bool
	allBinaries bool

	// Docker sub-tab
	docker       dockerStatus
	dockerProbed bool

	// Run state
	run     []*item
	current int
	spin    int
	onAbort bool

	// Log screen
	logIdx    int
	logScroll int
	logFollow bool

	// Patches / Settings / Deps
	patches []PatchInfo
	pcursor int
	scursor int
	deps    []depInfo
}

type tickMsg time.Time

func newModel(ctx *buildCtx) *model {
	return &model{
		ctx:      ctx,
		runner:   &runner{},
		menu:     menuTargets(),
		selected: map[string]bool{},
		patches:  scanPatches(ctx.scriptsRoot),
		deps:     scanDeps(ctx.scriptsRoot),
	}
}

func (m *model) Init() tea.Cmd { return tick() }

func tick() tea.Cmd {
	return tea.Tick(120*time.Millisecond, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func (m *model) buildActive() bool {
	for _, it := range m.run {
		if it.status == stQueued || it.status == stRunning {
			return true
		}
	}
	return false
}

// ── Selector grid geometry ───────────────────────────────────────────────────

type selColumn struct {
	group string
	items []int
}

// selBands lays the OS sections out as bands of side-by-side columns:
//
//	band 0: macOS · iOS
//	band 1: Windows · Linux · Android
//	band 2: Tools
func (m *model) selBands() [][]selColumn {
	col := func(g string) selColumn {
		var idx []int
		for i, t := range m.menu {
			if t.Group == g {
				idx = append(idx, i)
			}
		}
		return selColumn{g, idx}
	}
	return [][]selColumn{
		{col("macOS"), col("iOS")},
		{col("Windows"), col("Linux"), col("Android")},
		{col("Tools")},
	}
}

// gridBandRange returns the [lo, hi) band indices shown by the active build
// sub-tab: Compile shows the OS bands, Tools shows the actions band.
func (m *model) gridBandRange() (int, int) {
	if m.buildTab == 1 {
		return 2, 3
	}
	return 0, 2
}

// focusedIdx returns the menu index under the grid cursor.
func (m *model) focusedIdx() (int, bool) {
	bands := m.selBands()
	if m.selBand >= len(bands) {
		return 0, false
	}
	band := bands[m.selBand]
	if m.selCol >= len(band) {
		return 0, false
	}
	col := band[m.selCol]
	if m.selRow >= len(col.items) {
		return 0, false
	}
	return col.items[m.selRow], true
}

// isAction reports whether a menu index is a Tools run-button (not a checkbox).
func (m *model) isAction(idx int) bool { return m.menu[idx].Group == "Tools" }

// ── Hierarchical selection ───────────────────────────────────────────────────
//
// A group's "all" cell (Linux all, Android all, …) covers that group's
// per-arch cells; "All binaries" covers every cell. A covered cell shows
// checked but dimmed and can't be toggled.

// groupAllKey returns the key of a group's "all" target, or "".
func groupAllKey(group string) string {
	switch group {
	case "Android":
		return "android"
	case "Linux":
		return "linux"
	case "Windows":
		return "windows"
	}
	return ""
}

// groupPrimaryKey is the one target key that represents a whole group when
// "All binaries" is on.
func groupPrimaryKey(group string) string {
	switch group {
	case "macOS":
		return "macos"
	case "iOS":
		return "ios"
	}
	return groupAllKey(group)
}

func (m *model) cellCovered(idx int) bool {
	t := m.menu[idx]
	if !t.Available() || m.isAction(idx) {
		return false
	}
	if m.allBinaries {
		return true
	}
	if ga := groupAllKey(t.Group); ga != "" && ga != t.Key && m.selected[ga] {
		return true
	}
	return false
}

func (m *model) cellChecked(idx int) bool {
	return m.selected[m.menu[idx].Key] || m.cellCovered(idx)
}

// selectionKeys resolves the hierarchy into the concrete target keys to build.
func (m *model) selectionKeys() []string {
	if m.allBinaries {
		var keys []string
		seen := map[string]bool{}
		for _, t := range m.menu {
			if m.isAction(0) && t.Group == "Tools" {
				continue
			}
			k := groupPrimaryKey(t.Group)
			if k == "" || seen[k] {
				continue
			}
			if pt, ok := targetByKey(k); !ok || !pt.Available() {
				continue
			}
			seen[k] = true
			keys = append(keys, k)
		}
		return keys
	}
	var keys []string
	for i, t := range m.menu {
		if m.isAction(i) || !m.selected[t.Key] || m.cellCovered(i) {
			continue
		}
		keys = append(keys, t.Key)
	}
	return keys
}

func (m *model) selectedCount() int { return len(m.selectionKeys()) }

// ── Update ───────────────────────────────────────────────────────────────────

func (m *model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		return m, nil

	case tickMsg:
		m.spin++
		return m, tick()

	case lineMsg:
		if m.current < len(m.run) {
			it := m.run[m.current]
			it.cnt.add(classify(msg.line))
			it.log = append(it.log, msg.line)
			if len(it.log) > logKeep {
				it.log = it.log[len(it.log)-logKeep:]
			}
		}
		return m, nil

	case doneMsg:
		if m.current >= len(m.run) {
			return m, nil
		}
		it := m.run[m.current]
		it.ended = time.Now()
		if msg.err == nil {
			it.status = stOK
		} else {
			it.status = stFail
		}
		m.current++
		if m.current >= len(m.run) {
			return m, nil
		}
		if msg.err != nil && m.ctx.settings.SkipOnFailure {
			for i := m.current; i < len(m.run); i++ {
				m.run[i].status = stSkipped
			}
			m.current = len(m.run)
			return m, nil
		}
		return m, m.startCurrent()

	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	return m, nil
}

func (m *model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	if key == "ctrl+c" {
		if m.buildActive() {
			m.abortAll()
			return m, nil
		}
		return m, tea.Quit
	}

	// The header tab strip is GLOBAL: once the cursor is up on it (↑ from the
	// top of any section's content) its keys are handled here, whatever the
	// screen underneath.
	if m.onTabs {
		return m.keyHeaderTabs(key)
	}

	switch m.screen {
	case scDash:
		return m.keyDash(key)
	case scLog:
		return m.keyLog(key)
	case scPatches:
		return m.keyPatches(key)
	case scSettings:
		return m.keySettings(key)
	case scDeps:
		return m.keyDeps(key)
	default:
		return m.keySelect(key)
	}
}

// ── Global header tab strip ──────────────────────────────────────────────────
// The Build/Patches/Settings/Dependencies strip is fixed at the top of every
// section. Reached by pressing ↑ at the top of the content; there is a single
// cursor, so when the strip is focused the content shows no selection.

// enterHeaderTabs moves the single cursor up into the top tab strip, starting
// on the current section's tab.
func (m *model) enterHeaderTabs() {
	m.onTabs = true
	m.onAllBin = false
	m.onBuildTabs = false
	m.onBuild = false
	m.tabCur = sectionIndex(m.screen)
}

// dropIntoContent moves the cursor from the strip back down into the current
// section's content (the level just below the header).
func (m *model) dropIntoContent() {
	m.onTabs = false
	if m.screen == scSelect {
		m.onBuildTabs = true // land on the Compile/Tools/Docker sub-tab strip
	}
}

// switchSectionDir navigates to the adjacent section (←→ on the header
// strip), keeping the cursor on the strip so you can keep moving — the
// section underneath switches live.
func (m *model) switchSectionDir(dir int) {
	next := sectionIndex(m.screen) + dir
	if next < 0 || next >= len(topTabs) {
		return // clamp at the ends
	}
	m.screen = screenForTab(next)
	m.enterHeaderTabs()
}

// keyHeaderTabs handles navigation while the cursor is in the top tab strip,
// on any of the top screens. ←→ switches section live; ↓/⏎ drops into the
// section's content.
func (m *model) keyHeaderTabs(key string) (tea.Model, tea.Cmd) {
	switch key {
	case "left", "h":
		m.switchSectionDir(-1)
	case "right", "l":
		m.switchSectionDir(1)
	case "down", "j", "enter", " ", "esc", "q":
		m.dropIntoContent()
	}
	return m, nil
}

// switchSection jumps between the top-level sections (blocked mid-build).
func (m *model) switchSection(key string) (bool, screen) {
	if m.buildActive() {
		return false, m.screen
	}
	switch key {
	case "b":
		return true, scSelect
	case "p":
		return true, scPatches
	case "s":
		return true, scSettings
	case "d":
		return true, scDeps
	}
	return false, m.screen
}

func (m *model) keySelect(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		m.onTabs = false
		return m, nil
	}

	bands := m.selBands()
	lo, hi := m.gridBandRange()

	// Sub-tab strip (Compile | Tools | Docker)
	if m.onBuildTabs {
		switch key {
		case "left", "h":
			m.buildTab = clampInt(m.buildTab-1, 0, 2)
		case "right", "l":
			m.buildTab = clampInt(m.buildTab+1, 0, 2)
		case "up", "k":
			m.enterHeaderTabs()
		case "down", "j", "enter", " ":
			m.onBuildTabs = false
			switch m.buildTab {
			case 0:
				m.onAllBin = true
			case 1:
				m.selBand, m.selCol, m.selRow = 2, 0, 0
			case 2:
				m.probeDockerOnce()
			}
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// "All binaries" master row
	if m.onAllBin {
		switch key {
		case " ":
			m.allBinaries = !m.allBinaries
		case "up", "k":
			m.onAllBin = false
			m.onBuildTabs = true
		case "down", "j":
			m.onAllBin = false
			m.selBand, m.selCol, m.selRow = lo, 0, 0
		case "enter":
			return m, m.startBuild()
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// Build button
	if m.onBuild {
		switch key {
		case "enter", " ":
			return m, m.startBuild()
		case "up", "k":
			m.onBuild = false
			m.selBand = hi - 1
			m.selCol, m.selRow = 0, 0
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// Docker sub-tab body
	if m.buildTab == 2 {
		switch key {
		case "up", "k", "esc":
			m.onBuildTabs = true
		case "enter", " ":
			if m.docker.Exists {
				_ = deleteDockerImage()
				m.docker = probeDocker()
			} else {
				return m, m.startKeys([]string{"docker-image"})
			}
		case "r":
			m.docker = probeDocker()
		case "q":
			return m, tea.Quit
		}
		return m, nil
	}

	// Grid navigation
	clampRow := func() {
		col := bands[m.selBand][m.selCol]
		m.selRow = clampInt(m.selRow, 0, len(col.items)-1)
	}
	switch key {
	case "up", "k":
		if m.selRow > 0 {
			m.selRow--
		} else if m.selBand > lo {
			m.selBand--
			m.selCol = clampInt(m.selCol, 0, len(bands[m.selBand])-1)
			m.selRow = len(bands[m.selBand][m.selCol].items) - 1
		} else if m.buildTab == 0 {
			m.onAllBin = true
		} else {
			m.onBuildTabs = true
		}
	case "down", "j":
		col := bands[m.selBand][m.selCol]
		if m.selRow < len(col.items)-1 {
			m.selRow++
		} else if m.selBand < hi-1 {
			m.selBand++
			m.selCol = clampInt(m.selCol, 0, len(bands[m.selBand])-1)
			m.selRow = 0
		} else {
			m.onBuild = true
		}
	case "left", "h":
		if m.selCol > 0 {
			m.selCol--
			clampRow()
		}
	case "right", "l":
		if m.selCol < len(bands[m.selBand])-1 {
			m.selCol++
			clampRow()
		}
	case " ":
		if idx, ok := m.focusedIdx(); ok {
			t := m.menu[idx]
			if m.isAction(idx) {
				return m, m.startKeys([]string{t.Key})
			}
			if t.Available() && !m.cellCovered(idx) {
				m.selected[t.Key] = !m.selected[t.Key]
			}
		}
	case "a":
		m.allBinaries = !m.allBinaries
	case "enter":
		return m, m.startBuild()
	case "esc":
		m.onBuildTabs = true
	case "q":
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keyDash(key string) (tea.Model, tea.Cmd) {
	active := m.buildActive()
	switch key {
	case "q":
		if active {
			m.abortAll()
			return m, nil
		}
		return m, tea.Quit
	case "c":
		if active {
			m.abortAll()
		}
		return m, nil
	case "esc":
		if !active {
			m.screen = scSelect
		}
		return m, nil
	case "up", "k":
		m.logIdx = clampInt(m.logIdx-1, 0, len(m.run)-1)
	case "down", "j":
		if m.onAbort {
			return m, nil
		}
		m.logIdx = clampInt(m.logIdx+1, 0, len(m.run)-1)
	case "tab":
		if active {
			m.onAbort = !m.onAbort
		}
	case "enter", " ":
		if m.onAbort && active {
			m.abortAll()
			m.onAbort = false
			return m, nil
		}
		m.openLog(m.logIdx)
	}
	return m, nil
}

func (m *model) keyLog(key string) (tea.Model, tea.Cmd) {
	it := m.run[m.logIdx]
	page := maxInt(1, m.logWindowHeight())
	switch key {
	case "esc", "enter":
		m.screen = scDash
	case "up", "k":
		m.logFollow = false
		m.logScroll = clampInt(m.logScroll-1, 0, m.maxScroll(it))
	case "down", "j":
		m.logScroll = clampInt(m.logScroll+1, 0, m.maxScroll(it))
	case "pgup":
		m.logFollow = false
		m.logScroll = clampInt(m.logScroll-page, 0, m.maxScroll(it))
	case "pgdown":
		m.logScroll = clampInt(m.logScroll+page, 0, m.maxScroll(it))
	case "g":
		m.logFollow = false
		m.logScroll = 0
	case "G", "f":
		m.logFollow = true
	case "q":
		if m.buildActive() {
			m.abortAll()
			return m, nil
		}
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keyPatches(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		return m, nil
	}
	switch key {
	case "up", "k":
		if m.pcursor == 0 {
			m.enterHeaderTabs()
		} else {
			m.pcursor--
		}
	case "down", "j":
		m.pcursor = clampInt(m.pcursor+1, 0, len(m.patches)-1)
	case "esc":
		m.enterHeaderTabs()
	case "q":
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keySettings(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		return m, nil
	}
	switch key {
	case "up", "k":
		if m.scursor == 0 {
			m.enterHeaderTabs()
		} else {
			m.scursor--
		}
	case "down", "j":
		m.scursor = clampInt(m.scursor+1, 0, settingsRows()-1)
	case " ", "enter":
		m.toggleSettingAt(m.scursor)
	case "esc":
		m.enterHeaderTabs()
	case "q":
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) keyDeps(key string) (tea.Model, tea.Cmd) {
	if ok, sc := m.switchSection(key); ok {
		m.screen = sc
		return m, nil
	}
	switch key {
	case "up", "k", "esc":
		m.enterHeaderTabs()
	case "q":
		return m, tea.Quit
	}
	return m, nil
}

// ── Run orchestration ────────────────────────────────────────────────────────

func (m *model) startBuild() tea.Cmd {
	return m.startKeys(m.selectionKeys())
}

func (m *model) startKeys(keys []string) tea.Cmd {
	if len(keys) == 0 {
		return nil
	}
	queue, err := m.ctx.expand(keys)
	if err != nil {
		return nil
	}
	m.run = nil
	for _, t := range queue {
		m.run = append(m.run, &item{t: t})
	}
	m.current = 0
	m.logIdx = 0
	m.onAbort = false
	m.screen = scDash
	return m.startCurrent()
}

func (m *model) startCurrent() tea.Cmd {
	it := m.run[m.current]
	it.status = stRunning
	it.started = time.Now()
	go m.runner.start(m.program, m.ctx, it.t)
	return nil
}

func (m *model) abortAll() {
	m.runner.abort()
	for i := m.current + 1; i < len(m.run); i++ {
		m.run[i].status = stSkipped
	}
}

func (m *model) probeDockerOnce() {
	if !m.dockerProbed {
		m.docker = probeDocker()
		m.dockerProbed = true
	}
}

func (m *model) progress() (done, total int) {
	for _, it := range m.run {
		if it.status == stOK || it.status == stFail || it.status == stSkipped {
			done++
		}
	}
	return done, len(m.run)
}

// cellRunItems returns the run items a grid cell represents: its own key, or
// its members when it is a group "all" aggregate.
func (m *model) cellRunItems(idx int) []*item {
	t := m.menu[idx]
	keys := map[string]bool{t.Key: true}
	if full, ok := targetByKey(t.Key); ok {
		for _, mk := range full.members {
			keys[mk] = true
			if mt, ok2 := targetByKey(mk); ok2 {
				for _, mk2 := range mt.members {
					keys[mk2] = true
				}
			}
		}
	}
	var out []*item
	for _, it := range m.run {
		if keys[it.t.Key] {
			out = append(out, it)
		}
	}
	return out
}

// auxItems are run items with no grid cell (the docker-image prep step).
func (m *model) auxItems() []*item {
	var out []*item
	for _, it := range m.run {
		if it.t.kind == kImage {
			out = append(out, it)
		}
	}
	return out
}

func combinedStatus(items []*item) tstatus {
	st := stOK
	sawQueued := false
	for _, it := range items {
		switch it.status {
		case stRunning:
			return stRunning
		case stFail:
			st = stFail
		case stQueued, stSkipped:
			sawQueued = true
		}
	}
	if sawQueued && st == stOK {
		return stQueued
	}
	return st
}

func (m *model) glyphFor(st tstatus) (string, lipgloss.Style) {
	switch st {
	case stRunning:
		return spinnerFrames[m.spin%len(spinnerFrames)], runStyle
	case stOK:
		return "✓", okStyle
	case stFail:
		return "✗", failStyle
	case stSkipped:
		return "–", faintStyle
	default:
		return "·", dimStyle
	}
}

func statusWord(st tstatus) string {
	switch st {
	case stRunning:
		return "building"
	case stOK:
		return "done"
	case stFail:
		return "failed"
	case stSkipped:
		return "skipped"
	default:
		return "queued"
	}
}

func (m *model) timeCell(it *item) string {
	switch it.status {
	case stRunning:
		return time.Since(it.started).Round(time.Second).String()
	case stOK, stFail:
		return it.ended.Sub(it.started).Round(time.Second).String()
	}
	return ""
}

// ── Views ────────────────────────────────────────────────────────────────────

func (m *model) View() string {
	switch m.screen {
	case scDash:
		return m.viewDash()
	case scLog:
		return m.viewLog()
	case scPatches:
		return m.viewPatches()
	case scSettings:
		return m.viewSettings()
	case scDeps:
		return m.viewDeps()
	default:
		return m.viewSelect()
	}
}

// renderBuildTabStrip draws the Compile | Tools | Docker sub-tab row.
func (m *model) renderBuildTabStrip(focused bool) string {
	labels := []string{"Compile", "Tools", "Docker"}
	cells := make([]string, len(labels))
	for i, l := range labels {
		switch {
		case focused && i == m.buildTab:
			cells[i] = tabFocusStyle.Render(l)
		case i == m.buildTab:
			cells[i] = subTabActiveStyle.Render(l)
		default:
			cells[i] = tabInactiveStyle.Render(l)
		}
	}
	return lipgloss.JoinHorizontal(lipgloss.Center, cells...)
}

// gridCellW / gridRowW are the fixed cell geometry shared by the selector and
// the build grid so the two layouts line up exactly.
const (
	gridCellW = 22            // label area inside a cell
	gridRowW  = 2 + gridCellW // leading marker + cell

	// dashRowW is the cell width inside the dashboard's per-OS boxes —
	// narrower than the selector cells so three boxed columns fit an
	// 80-column terminal with their rounded borders + padding.
	dashRowW = 20
)

// renderBandRange renders grid bands [lo,hi) as side-by-side columns.
func (m *model) renderBandRange(cell func(idx int, focused bool) string, cursorInGrid bool, lo, hi int, showHeaders bool) string {
	bands := m.selBands()
	var b strings.Builder
	for bi := lo; bi < hi && bi < len(bands); bi++ {
		band := bands[bi]
		var cols []string
		for ci, c := range band {
			var cb strings.Builder
			if showHeaders {
				writeLine(&cb, hdrStyle.Render(padTrunc(c.group, gridRowW)))
			}
			for ri, idx := range c.items {
				focused := cursorInGrid && m.selBand == bi && m.selCol == ci && m.selRow == ri
				writeLine(&cb, cell(idx, focused))
			}
			cols = append(cols, cb.String())
		}
		writeLine(&b, lipgloss.JoinHorizontal(lipgloss.Top, cols...))
	}
	return b.String()
}

func (m *model) viewSelect() string {
	var b strings.Builder
	focus := -1
	if m.onTabs {
		focus = m.tabCur
	}
	writeLine(&b, renderHeader(0, focus, m.width, false))

	sel := m.selectedCount()

	writeLine(&b, m.renderBuildTabStrip(m.onBuildTabs))
	b.WriteByte('\n')

	cursorInGrid := !m.onBuild && !m.onTabs && !m.onAllBin && !m.onBuildTabs

	okRow := lipgloss.NewStyle().Foreground(cOK)
	row := func(idx int, focused bool) string {
		t := m.menu[idx]
		avail := t.Available()

		// Action cells (run buttons, not checkboxes): the label on the left, a
		// dim one-line description on the right.
		if m.isAction(idx) {
			const actLabelW = 11
			if focused {
				line := "▷ " + padTrunc(t.Label, actLabelW) + t.Desc
				return hiStyle.Render(padTrunc(line, maxInt(1, m.width-2)))
			}
			label, descW := "  "+padTrunc(t.Label, actLabelW), maxInt(1, m.width-actLabelW-4)
			if !avail {
				return dimStyle.Render(label + truncate(t.Desc, descW))
			}
			return lipgloss.NewStyle().Foreground(cAccent2).Render(label) +
				dimStyle.Render(truncate(t.Desc, descW))
		}

		checked := m.cellChecked(idx)
		covered := m.cellCovered(idx)
		check := boxOff
		switch {
		case !avail:
			check = boxNA
		case checked:
			check = boxOn
		}
		var line string
		if focused {
			line = padTrunc("▷ "+check+" "+t.Label, gridRowW)
		} else {
			line = "  " + padTrunc(check+" "+t.Label, gridCellW)
		}
		switch {
		case focused:
			return hiStyle.Render(line)
		case !avail:
			return dimStyle.Render(line)
		case covered:
			return faintStyle.Render(line) // selected but covered → opaque, locked
		case checked:
			return okRow.Render(line)
		default:
			return line
		}
	}

	switch m.buildTab {
	case 0:
		// ── Compile: All binaries + the OS grid + Build button ──
		abCheck := boxOff
		if m.allBinaries {
			abCheck = boxOn
		}
		switch {
		case m.onAllBin:
			writeLine(&b, hiStyle.Render(padTrunc("▷ "+abCheck+" All binaries  — every available target", maxInt(1, m.width-2))))
			b.WriteByte('\n')
		case m.allBinaries:
			writeLine(&b, okStyle.Bold(true).Render("  "+abCheck+" All binaries"), dimStyle.Render("  — every available target"))
			b.WriteByte('\n')
		default:
			writeLine(&b, "  ", abCheck, " All binaries", dimStyle.Render("  — every available target"))
			b.WriteByte('\n')
		}
		b.WriteString(m.renderBandRange(row, cursorInGrid, 0, 2, true))

		label := fmt.Sprintf("Build (%d selected)", sel)
		switch {
		case m.onBuild:
			writeLine(&b, buildBtnFocusStyle.Render(label))
		case sel == 0:
			writeLine(&b, buildBtnDisabledStyle.Render(label))
		default:
			writeLine(&b, buildBtnStyle.Render(label))
		}
	case 1:
		// ── Tools: one-shot actions ──
		b.WriteString(m.renderBandRange(row, cursorInGrid, 2, 3, false))
	default:
		// ── Docker: build-env image management ──
		b.WriteString(m.renderDockerTab())
	}

	b.WriteString("\n")
	if idx, ok := m.focusedIdx(); ok && cursorInGrid && !m.menu[idx].Available() {
		writeLine(&b, warnStyle.Render("⚠ "+m.menu[idx].unavailReason()))
	}
	var help string
	switch {
	case m.onTabs:
		help = helpBar(
			[2]string{"←→", "switch section"},
			[2]string{"↓", "down"},
			[2]string{"esc", "back"},
		)
	case m.onBuildTabs:
		help = helpBar(
			[2]string{"←→", "Compile/Tools/Docker"},
			[2]string{"↓", "into tab"},
			[2]string{"↑", "sections"},
			[2]string{"q", "quit"},
		)
	case m.buildTab == 2:
		act := "build image"
		if m.docker.Exists {
			act = "delete image"
		}
		help = helpBar(
			[2]string{"⏎", act},
			[2]string{"r", "refresh"},
			[2]string{"esc", "tabs"},
			[2]string{"q", "quit"},
		)
	case m.onAllBin:
		help = helpBar(
			[2]string{"space", "toggle all"},
			[2]string{"↓", "targets"},
			[2]string{"↑", "tabs"},
			[2]string{"q", "quit"},
		)
	default:
		space := "toggle"
		if idx, ok := m.focusedIdx(); ok && m.isAction(idx) {
			space = "run"
		}
		help = helpBar(
			[2]string{"↑↓←→", "move"},
			[2]string{"space", space},
			[2]string{"a", "all"},
			[2]string{"⏎", "build"},
			[2]string{"p/s/d", "patches/settings/deps"},
			[2]string{"q", "quit"},
		)
	}
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+help)
}

// renderDashBoxes lays out the dashboard grid with each OS group wrapped in a
// rounded box — the OS name as the box title, its per-arch rows inside, the
// border tinted by the group's combined run status: running (blue), done
// (green), failed (red); groups not part of the run keep a faint idle border.
func (m *model) renderDashBoxes(cell func(idx int) string) string {
	bands := m.selBands()
	var b strings.Builder
	for bi := 0; bi < 2 && bi < len(bands); bi++ {
		var cols []string
		for _, c := range bands[bi] {
			borderColor := cBorder
			titleSt := faintStyle
			var items []*item
			for _, idx := range c.items {
				items = append(items, m.cellRunItems(idx)...)
			}
			if len(items) > 0 {
				switch combinedStatus(items) {
				case stRunning:
					borderColor, titleSt = cRun, runStyle
				case stOK:
					borderColor, titleSt = cOK, okStyle
				case stFail:
					borderColor, titleSt = cFail, failStyle
				}
			}
			var cb strings.Builder
			writeLine(&cb, titleSt.Bold(true).Render(padTrunc(c.group, dashRowW)))
			for _, idx := range c.items {
				writeLine(&cb, cell(idx))
			}
			box := lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(borderColor).
				Padding(0, 1).
				Render(strings.TrimRight(cb.String(), "\n"))
			cols = append(cols, box)
		}
		writeLine(&b, lipgloss.JoinHorizontal(lipgloss.Top, cols...))
	}
	return b.String()
}

func (m *model) viewDash() string {
	var b strings.Builder
	locked := m.buildActive()
	writeLine(&b, renderHeader(0, -1, m.width, locked))

	// progress summary: bar + done count + total ℹ/⚠/✗ across all builds
	done, total := m.progress()
	var ti, tw, te int
	for _, it := range m.run {
		ti += it.cnt.info
		tw += it.cnt.warn
		te += it.cnt.errs
	}
	bar := progressBar(done, total, clampInt(m.width/3, 8, 40))
	writeLine(&b,
		bar,
		"  ",
		dimStyle.Render(fmt.Sprintf("%d/%d done", done, total)),
		dimStyle.Render("   "),
		counterBar(ti, tw, te),
	)

	// aux run items that have no grid cell (the docker-image prep step)
	if aux := m.auxItems(); len(aux) > 0 {
		b.WriteString("\n")
		for _, it := range aux {
			glyph, gstyle := m.glyphFor(it.status)
			label := "build-env image"
			if it.status == stRunning {
				if cur := lastLogLine(it); cur != "" {
					label += "  ·  " + cur
				}
			}
			text := label + "  " + m.timeCell(it)
			writeLine(&b, gstyle.Render(glyph), " ", dimStyle.Render(truncate(text, maxInt(8, m.width-2))))
		}
	}
	b.WriteString("\n")

	// the grid, run-mode cells
	cell := func(idx int) string {
		t := m.menu[idx]
		items := m.cellRunItems(idx)
		inRun := len(items) > 0
		glyph, gstyle := "·", faintStyle
		if inRun {
			glyph, gstyle = m.glyphFor(combinedStatus(items))
		}
		ls := faintStyle
		if inRun {
			ls = textStyle
		}
		return gstyle.Render(glyph) + " " + ls.Render(padTrunc(t.Label, dashRowW-2))
	}
	b.WriteString(m.renderDashBoxes(cell))

	// focused run item readout + selector
	b.WriteString("\n")
	for i, it := range m.run {
		glyph, gstyle := m.glyphFor(it.status)
		line := gstyle.Render(glyph+" "+it.t.fullLabel()) +
			dimStyle.Render("    "+statusWord(it.status)) +
			dimStyle.Render("    "+m.timeCell(it)) +
			dimStyle.Render("    ") + counterBar(it.cnt.info, it.cnt.warn, it.cnt.errs)
		if i == m.logIdx && !m.onAbort {
			line = hiStyle.Render("▷ ") + line
		} else {
			line = "  " + line
		}
		writeLine(&b, truncate(line, maxInt(20, m.width)))
	}

	// Red Abort button — cancels the running + queued builds.
	if m.buildActive() {
		label := "✕ Abort all builds"
		b.WriteByte('\n')
		if m.onAbort {
			writeLine(&b, abortBtnFocusStyle.Render(label))
		} else {
			writeLine(&b, abortBtnStyle.Render(label))
		}
	}

	enterHint := [2]string{"⏎", "view log"}
	if m.onAbort {
		enterHint = [2]string{"⏎", "abort all"}
	}
	pairs := [][2]string{
		{"↑↓", "move"},
		enterHint,
	}
	if m.buildActive() {
		pairs = append(pairs, [2]string{"tab", "abort btn"}, [2]string{"c", "cancel"})
	} else {
		pairs = append(pairs, [2]string{"esc", "back"})
	}
	pairs = append(pairs, [2]string{"q", "quit"})
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+helpBar(pairs...))
}

// lastLogLine returns the most recent non-empty line of an item's captured
// output (used to surface a docker build's current step live).
func lastLogLine(it *item) string {
	for i := len(it.log) - 1; i >= 0; i-- {
		if s := strings.TrimSpace(it.log[i]); s != "" {
			return s
		}
	}
	return ""
}

// ── Log screen ───────────────────────────────────────────────────────────────

func (m *model) logWindowHeight() int {
	return maxInt(4, m.height-6)
}

func (m *model) maxScroll(it *item) int {
	return maxInt(0, len(it.log)-m.logWindowHeight())
}

func (m *model) openLog(ri int) {
	if ri < 0 || ri >= len(m.run) {
		return
	}
	m.screen = scLog
	m.logIdx = ri
	m.logFollow = true
	m.logScroll = m.maxScroll(m.run[ri])
}

func (m *model) viewLog() string {
	it := m.run[m.logIdx]
	var b strings.Builder
	writeLine(&b, renderHeader(0, -1, m.width, m.buildActive()))

	glyph, gstyle := m.glyphFor(it.status)
	writeLine(&b,
		gstyle.Render(glyph+" "+it.t.fullLabel()),
		dimStyle.Render("   "+statusWord(it.status)+"   "+m.timeCell(it)+"   "),
		counterBar(it.cnt.info, it.cnt.warn, it.cnt.errs),
	)
	b.WriteByte('\n')

	if m.logFollow {
		m.logScroll = m.maxScroll(it)
	}
	h := m.logWindowHeight()
	lines := make([]string, len(it.log))
	for i, l := range it.log {
		lines[i] = logStyle.Render(truncate(l, maxInt(8, m.width-4)))
	}
	b.WriteString(scrollView(lines, h, m.logScroll))

	follow := "follow"
	if m.logFollow {
		follow = "following"
	}
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+helpBar(
		[2]string{"↑↓", "scroll"},
		[2]string{"g/G", "top/bottom"},
		[2]string{"f", follow},
		[2]string{"esc", "back"},
		[2]string{"q", "quit"},
	))
}

// ── Patches screen ───────────────────────────────────────────────────────────

func (m *model) viewPatches() string {
	var b strings.Builder
	focus := -1
	if m.onTabs {
		focus = m.tabCur
	}
	writeLine(&b, renderHeader(1, focus, m.width, false))

	if len(m.patches) == 0 {
		writeLine(&b, dimStyle.Render("no patches found under patches/libsmb2/"))
		return m.anchorBottom(b.String(), hrule(m.width)+"\n"+helpBar([2]string{"b", "build"}, [2]string{"q", "quit"}))
	}
	scope := ""
	listRows := 0
	for i, p := range m.patches {
		if p.Scope != scope {
			scope = p.Scope
			writeLine(&b, hdrStyle.Render(scope))
			listRows++
		}
		line := fmt.Sprintf("  %-32s %s", p.Name, truncate(p.Title, maxInt(8, m.width-38)))
		if i == m.pcursor && !m.onTabs {
			writeLine(&b, hiStyle.Render(padTrunc("▷"+line[1:], maxInt(1, m.width-2))))
		} else {
			writeLine(&b, textStyle.Render(line))
		}
		listRows++
	}
	writeLine(&b)

	// Detail panel for the focused patch, WINDOWED to the space left below the
	// list: the whole screen must never exceed the terminal height, or the
	// fixed header scrolls out of view.
	p := m.patches[m.pcursor]
	width := maxInt(20, m.width-4)
	inner := maxInt(10, width-2) // inside the panel borders/padding
	lines := []string{titleStyle.Render(truncate(p.Title, inner))}
	if p.Body != "" {
		lines = append(lines, "")
		for _, l := range strings.Split(p.Body, "\n") {
			lines = append(lines, logStyle.Render(truncate(l, inner)))
		}
	}
	if m.height > 0 {
		// header(2) + list + blank + panel borders(2) + rule + help + margin(2)
		avail := m.height - 2 - listRows - 1 - 2 - 2 - 2
		if avail < 3 {
			avail = 3
		}
		if len(lines) > avail {
			lines = append(lines[:avail-1], dimStyle.Render("… ↑↓ another patch, or widen the terminal"))
		}
	}
	writeLine(&b, panelStyle.Width(width).Render(strings.Join(lines, "\n")))

	help := helpBar(
		[2]string{"↑↓", "browse"},
		[2]string{"b/s/d", "build/settings/deps"},
		[2]string{"q", "quit"},
	)
	if m.onTabs {
		help = helpBar(
			[2]string{"←→", "switch section"},
			[2]string{"↓", "down"},
			[2]string{"esc", "back"},
		)
	}
	return m.anchorBottom(b.String(), hrule(m.width)+"\n"+help)
}
