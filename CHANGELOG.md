## [0.1.2] - 18-08-2026

### Changed
- Re-architecture: libsmb2 is now fetched at build time from a pinned, SHA-256-verified upstream commit (master 2026-08-14) instead of a vendored tree — picking up upstream's August 2026 security hardening and the rewritten minimal DCE/RPC (the old code's unaligned accesses were the prime suspect for the arm32 crash in dart_smb2 [#2](https://github.com/ales-drnz/dart_smb2/issues/2)).
- Every local modification is a standalone, documented patch under `patches/libsmb2/`, applied at build time and failing loudly on upstream drift.

### Added
- `./build`: Go / Bubble Tea orchestrator — build dashboard, Patches / Settings / Dependencies / Docker sections, headless CLI. Replaces the Makefile.
- Verify: dlopen + FFI-symbol audit of the built binaries.

## [0.1.1] - 19-07-2026

### Added
- `smb2_utimes` / `smb2_utimes_async` patch backing dart_smb2's `setFileTimes`. Binaries: `libsmb2-r6`.

## [0.1.0] - 28-05-2026

### Added
- Initial build infrastructure, split out of `dart_smb2/scripts/`. Binaries: `libsmb2-r5`.
