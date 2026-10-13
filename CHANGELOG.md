## [0.2.0] - 13-10-2026

### Breaking
- `./build checksums`, `./build bump` and the `lib-local` / `lib-remote` / `lib-clean` switch are gone: a build ends in `release_builds/` with `manifest.json`, and dart_smb2 takes the hashes into its build hook with `tool/update_libsmb2.sh`. Building needs no dart_smb2 checkout.
- `src/smb2_wrapper.c`, unused since dart_smb2 0.1.0, is gone; each binary exports libsmb2's public API only.

### Added
- `.github/workflows/build.yml`: every push to a `release/` branch builds all nine binaries on GitHub's runners, Apple included (on `macos-26`, with Xcode 26.6 pinned through `DEVELOPER_DIR`), and verifies them on x86_64 and arm64. Its actions are pinned by commit SHA, on Node 24, and every job has a timeout.
- `manifest.json` and `SHA256SUMS` (`./build manifest`), written only when `release_builds/` holds exactly the nine binaries (`ALLOW_PARTIAL=1` writes one for a subset, with a warning).
- libsmb2's `COPYING` and `LICENCE-LGPL-2.1.txt` in `licenses/libsmb2/` and in every release: beside the binaries, listed in `SHA256SUMS` and under the `licenses` key of `manifest.json` (`assets` lists the binaries only), and inside both xcframework zips under `licenses/libsmb2/`. `verify` checks them.
- `patch_active_contexts_lock.py`: a lock around libsmb2's global context list, which dart_smb2's worker isolates change from several threads; `smb2_context_active()` takes it too, and so does the seed counter of `smb2_init_context()`, which ThreadSanitizer reported.
- `patch_rmdir_disposition.py`: `rmdir` fails with `STATUS_DIRECTORY_NOT_EMPTY` on a directory with entries and with `STATUS_NOT_A_DIRECTORY` on a file, instead of returning success and keeping the directory, or deleting the file.
- `patch_unlink_non_directory.py`: `unlink` on a directory fails with `STATUS_FILE_IS_A_DIRECTORY` (`-EPERM`) instead of deleting an empty one and returning success on one with entries. So does a link to a directory: on Windows a directory junction or symlink is now removed with `rmdir` (which removes the link, not its target), and a Samba symlink to a directory cannot be removed over SMB2 at all, since Samba follows it and libsmb2 does not negotiate the POSIX extensions. A symlink to a file is still removed.
- `patch_truncate_non_directory.py`: `truncate` on a directory fails with `STATUS_FILE_IS_A_DIRECTORY` instead of returning success and changing nothing.
- `patch_compound_callbacks.py`: a compound that times out or is dropped by `smb2_destroy_context()` before it is sent calls every PDU's callback, not the first only, so rmdir and unlink (and mkdir, stat, fstat, truncate, rename) report the timeout once and free their data, and the synchronous calls return `-ETIMEDOUT` instead of polling forever. `fstat`'s second callback, which read the reply before checking the status, now checks for one first: with the reply NULL on those paths, it was a NULL dereference (an ASan build crashed).
- `patch_create_data_leaks.py`: `unlink`, `mkdir` and `ftruncate` free their call data when their first request cannot be built (out of memory, or a path that is not valid UTF-8).

### Changed
- libsmb2 is upstream master of 11-10-2026 (e94eee9). Binaries: `libsmb2-r9`.
- `patch_nterror_reporting.py` also records the NT status of rename / link and echo failures, and the timeout sweep records `SMB2_STATUS_IO_TIMEOUT`, so a failure never reports the status of an earlier one.
- `verify` checks all nine binaries: exported symbols (`verify/symbols.txt`), machine, glibc floor, stripped libraries on every platform, Android alignment and dependencies, Windows imports, Apple slices and minimum OS, and the licence texts and `SHA256SUMS` of a release. It runs in its own Docker image.
- Docker has one stage per job, base images pinned by digest, llvm-mingw by SHA-256 and the Linux and Verify stages' apt packages at exact versions (the Windows stage's helper packages stay unpinned, and the Dockerfile says why); images are tagged with a hash of the Dockerfile and rebuilt when it changes, and containers run as the calling user.
- Linux builds on Ubuntu 20.04: the libraries reference no glibc symbol newer than `GLIBC_2.25` and are verified on 2.31, the floor `verify` enforces (r8 needed 2.38).
- Every library is stripped: Linux and Android keep only `.dynsym`, the Windows DLLs lose the static runtime's DWARF and their COFF symbol table (their export table stays), and the Apple frameworks link with `-Wl,-x`, which drops the local symbols as `strip -x` does.
- Windows builds both architectures with llvm-mingw and without a PE timestamp; with `LC_ALL=C` link order, Linux, Android and Windows builds are byte for byte reproducible.
- Android requires the pinned NDK unless `ALLOW_ANY_NDK=1`, and links libc only. Apple targets iOS 13.0 and macOS 10.15 and uses CommonCrypto for AES.
- `./build all` builds what this host can and skips the rest with a line saying why (Android too, when the pinned NDK is missing); it writes the manifest only when nothing was skipped. A target named explicitly that cannot run still fails, and so does a group named explicitly none of whose targets can.
- `JOBS` applies to every platform, and a failed compile stops the build.
- `export_sources.sh` points at dart_smb2's `tool/ffigen.dart` and `tool/bindings_drift.dart`.
- Each patch script states that its code is added to libsmb2 under the LGPL-2.1. The patches apply in any order with the same result; `patch_compound_callbacks.py` no longer needs to run before `patch_nterror_reporting.py`.

### Fixed
- `patch_windows_sockets.py` no longer widens `maxfd` in the server loop, which broke the build against upstream's new `extra_fdset` hook.

### Removed
- `patch_timeout_caller_frees.py` and `patch_sync_open_cb_data_leak.py`: upstream carries both fixes (b0b1e42, 7905719).
- `patch_windows_dcerpc_interface.py` and the `<io.h>` reordering of `patch_windows_headers.py`: they only mattered for the DCE/RPC code upstream moved to libdcerpc.

## [0.1.3] - 19-09-2026

### Fixed
- `smb2_timeout_pdus()` freed timed-out requests that the synchronous `smb2_open()` / `smb2_opendir()` still owned, so an open or directory listing that hit the timeout was freed twice and aborted the process (dart_smb2 [#3](https://github.com/ales-drnz/dart_smb2/issues/3), upstream [sahlberg/libsmb2#484](https://github.com/sahlberg/libsmb2/issues/484)). `patch_timeout_caller_frees.py` applies the `caller_frees_pdu` guard the reply path already uses.
- Every synchronous `smb2_open()` leaked its callback data: upstream takes a `free_cb` it never stores. `patch_sync_open_cb_data_leak.py` frees it in `smb2_open()`, which owns it.

### Added
- Libs source switch, as in libmpv-scripts: `lib-local` (install the built libs and never download), `lib-remote` (download from GitHub Releases) and `lib-clean` (remove the bundled libs), in the Tools row and on the command line. It comments / uncomments the `smb2kit:` marker regions it adds to dart_smb2's `build.gradle.kts`, both `CMakeLists.txt`, both podspecs and both `Package.swift`, so a locally built library is no longer silently replaced by the published one because its SHA-256 differs.

### Changed
- dart_smb2 `0.1.3`, binaries `libsmb2-r8`.

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
