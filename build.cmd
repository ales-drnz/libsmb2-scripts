@echo off
rem Copyright (c) 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
rem All rights reserved.
rem Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
rem
rem Windows entry point for the libsmb2 build orchestrator.
rem Only Docker targets (linux / windows) run on a Windows host.
where go >nul 2>nul || (
  echo Go not found — install it from https://go.dev/dl/ and re-run.
  exit /b 1
)
cd /d "%~dp0tui"
go mod tidy >nul 2>nul
go run . %*
