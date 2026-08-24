## [0.1.2] - 24-08-2026

### Changed
- libsmb2 is now fetched at build time from a pinned, SHA-256-verified upstream commit (master 2026-08-14) instead of a vendored tree, picking up upstream's August 2026 security hardening and the rewritten minimal DCE/RPC ([dart_smb2#2](https://github.com/ales-drnz/dart_smb2/issues/2)). Every local modification is a standalone, documented patch under `patches/libsmb2/`, applied at build time and failing loudly on upstream drift.

### Added
- `./build`: Go / Bubble Tea orchestrator with headless CLI, replacing the Makefile. Includes `verify` (dlopen + FFI-symbol audit) and `sources` (export the patched tree for dart_smb2's ffigen).

### Fixed
- Windows: build the r7 minimal DCE/RPC path against llvm-mingw. Upstream never compiles it there, so four collisions surfaced only here — `interface` is a reserved macro in mingw's `<rpc.h>`, the `asprintf`/`vasprintf` fallbacks redefine what modern mingw declares, `<io.h>` must precede the `close()` → `closesocket()` remap, and `compat.c` never included `config.h`.
- `generate_checksums.sh` silently skipped the Android SHA-256s (the regex assumed single-space alignment, and `perl` exits 0 either way). It now tolerates the spacing and verifies the hash landed.

### Security
- Windows: `smb2_random_bytes()` had no strong entropy source and fell back to `rand()`. Added CNG's `BCryptGenRandom` alongside upstream's `arc4random` / `getrandom` / `/dev/urandom`.

## [0.1.1] - 19-07-2026

### Added
- `smb2_utimes` / `smb2_utimes_async` patch backing dart_smb2's `setFileTimes`. Binaries: `libsmb2-r6`.

## [0.1.0] - 28-05-2026

### Added
- Initial build infrastructure, split out of `dart_smb2/scripts/`. Binaries: `libsmb2-r5`.
