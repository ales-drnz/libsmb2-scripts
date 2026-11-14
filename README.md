# libsmb2-scripts

#### Patched libsmb2, built for every platform.

[![](https://img.shields.io/badge/libsmb2--scripts-0.4.0-7DCFFF.svg?style=for-the-badge)](CHANGELOG.md)
[![](https://img.shields.io/badge/libsmb2-master%202026--11--07-orange.svg?style=for-the-badge)](https://github.com/sahlberg/libsmb2)
[![](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg?style=for-the-badge)](LICENSE)
[![](https://img.shields.io/github/stars/ales-drnz/libsmb2-scripts?style=for-the-badge&logo=github&logoColor=white)](https://github.com/ales-drnz/libsmb2-scripts)
[![](https://img.shields.io/discord/1485588004029333516?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/g2Qf4Mq9MP)
[![](https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/cw/ales_drnz)
[![](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/ales.drnz)

The build scripts for the libsmb2 inside [`dart_smb2`](https://pub.dev/packages/dart_smb2). They compile a pinned upstream [libsmb2](https://github.com/sahlberg/libsmb2) commit with a small set of patches the package relies on, and link it with [OpenSSL](https://www.openssl.org)'s libcrypto, for macOS, iOS, Android, Windows and Linux.

Everything runs from `./build`, a terminal menu where you pick the targets and follow the builds. This repository is also the corresponding source of the LGPL-2.1 binaries `dart_smb2` ships (see [Licensing](#licensing)).

---

## Quick start

```bash
git clone https://github.com/ales-drnz/libsmb2-scripts
cd libsmb2-scripts
./build
```

On Windows use `build.cmd`. You need Go, plus Docker for Linux and Windows, the Android NDK for Android, and Xcode for Apple targets; Android and Apple builds also need perl and make.

---

## What it produces

| Platform | Architectures | File in `release_builds/` |
| :--- | :--- | :--- |
| macOS | arm64 and x86_64 (universal) | `libsmb2_macos.xcframework.zip` |
| iOS | arm64 device, arm64 and x86_64 simulator | `libsmb2_ios.xcframework.zip` |
| Android | arm64-v8a, armeabi-v7a, x86_64 | `libsmb2_android-<abi>.so` |
| Linux | x86_64, aarch64 | `libsmb2_linux-<arch>.so` |
| Windows | x86_64, arm64 | `libsmb2_windows-<arch>.dll` |

Each library links OpenSSL 3.5's libcrypto statically, built from the pinned release tarball with only what libsmb2 uses: libsmb2 signs and seals through it, with AES-256-GCM and AES-128-GCM on SMB 3.1.1. This makes the libraries larger, 1.3 to 3.5 MB per architecture instead of about 0.25 MB; the Windows arm64 libcrypto is built without assembly, as OpenSSL has no mingw target for arm64. Each library exports libsmb2's public API (`lib/libsmb2.syms`) and nothing else, none of libcrypto's, and has no SONAME, so the app bundles it under its own name. Each one states the release it was built as: `smb2_scripts_release()` returns `LIBSMB2_RELEASE` (`"r12"`), the same string on every platform, and `dart_smb2` refuses a libsmb2 that names another release or lacks the call. The Linux ones reference no glibc symbol newer than 2.25 and are built and tested on glibc 2.31, the oldest supported; the Android ones depend on libc only and align their 64-bit segments to 16 KB; the Windows ones import only system DLLs; all of them are stripped: the Linux and Android ones keep only the dynamic symbol table, the Windows ones carry no DWARF and no COFF symbol table beside their export table, and the Apple ones have no local symbols; the Apple ones target iOS 13.0 and macOS 10.15.

The libsmb2 commit, the OpenSSL version and the SHA-256 of both tarballs are set in `scripts/shared/_versions.sh`, the Docker base images are pinned by digest, llvm-mingw by SHA-256 and the apt packages of the Linux and Verify images by version, and the Android NDK is pinned by version. Linux, Android and Windows builds give the same bytes on any machine. The xcframework zips list their entries in byte order with every time set to `SOURCE_DATE_EPOCH` (1-1-2026 when unset), and sort the slices in `Info.plist`, so neither the build time nor the checkout time reaches them. The Apple libraries themselves give the same bytes for the same Xcode only, so per CI runner image: each slice records the SDK and linker version (`LC_BUILD_VERSION`), and the compiler differs between Xcode releases. OpenSSL also records its compile flags, the SDK path among them, in libcrypto; libsmb2 never calls `OpenSSL_version()`, so that string is not linked into the libraries today. `./build manifest` writes `release_builds/manifest.json` and `SHA256SUMS` once all nine libraries are there (CI always builds all nine), with the release, the libsmb2 and OpenSSL pins, the source commit, the patches, the verified symbols and the hash of every library, and copies libsmb2's licence texts (`COPYING`, `LICENCE-LGPL-2.1.txt`) and OpenSSL's (`LICENSE-OpenSSL.txt`) beside them; the xcframework zips carry them too.

---

## Contents

*   [Quick start](#quick-start)
*   [What it produces](#what-it-produces)
*   [Guide](#guide)
    <details>
    <summary><a href="#1-requirements"><b>1. Requirements</b></a></summary>

    * [1.1 Tools](#11-tools)
    * [1.2 What each host can build](#12-what-each-host-can-build)
    * [1.3 Folder layout](#13-folder-layout)

    </details>

    <details>
    <summary><a href="#2-the-menu"><b>2. The menu</b></a></summary>

    * [2.1 Build](#21-build)
    * [2.2 Patches](#22-patches)

    </details>

    <details>
    <summary><a href="#3-building"><b>3. Building</b></a></summary>

    * [3.1 macOS and iOS](#31-macos-and-ios)
    * [3.2 Linux and Windows](#32-linux-and-windows)
    * [3.3 Android](#33-android)
    * [3.4 From the command line](#34-from-the-command-line)
    * [3.5 On GitHub Actions](#35-on-github-actions)

    </details>

    <details>
    <summary><a href="#4-using-the-binaries"><b>4. Using the binaries</b></a></summary>

    * [4.1 Installing into dart_smb2](#41-installing-into-dart_smb2)
    * [4.2 Local libraries in an app](#42-local-libraries-in-an-app)
    * [4.3 Verifying](#43-verifying)
    * [4.4 Publishing a release](#44-publishing-a-release)

    </details>

    <details>
    <summary><a href="#5-how-it-works"><b>5. How it works</b></a></summary>

    * [5.1 The patch set](#51-the-patch-set)
    * [5.2 Bumping upstream libsmb2](#52-bumping-upstream-libsmb2)

    </details>
*   [Troubleshooting](#troubleshooting)
*   [Licensing](#licensing)
*   [Project background](#project-background)

---

## Guide

### 1. Requirements

#### 1.1 Tools

| Tool | Needed for |
| :--- | :--- |
| [Go](https://go.dev/dl/) | always, it runs `./build` |
| [Docker](https://docs.docker.com/get-docker/) | Linux, Windows and Verify |
| Android NDK 28.2.13676358 (r28c) | Android, from the Android Studio SDK Manager |
| Xcode | macOS and iOS |
| perl and make | Android, macOS and iOS, for OpenSSL's `Configure` (Xcode's command line tools have both; the Docker images bring their own) |

#### 1.2 What each host can build

| Host | Targets |
| :--- | :--- |
| macOS | all of them |
| Linux | all except macOS and iOS (Android with the NDK) |
| Windows | Linux and Windows |

Apple targets need a Mac. [GitHub Actions](#35-on-github-actions) builds everything, whatever you have.

#### 1.3 Folder layout

Building needs only this repo. The libraries, `manifest.json`, `SHA256SUMS` and the licence texts land in `release_builds/`; the pinned libsmb2 and OpenSSL tarballs are cached in `sources/cache/`; `./build sources` writes the patched tree that `dart_smb2`'s `tool/ffigen.dart` reads to `sources/libsmb2-src/`.

---

### 2. The menu

Run `./build`. Arrow keys move, Space selects, Enter confirms, Q quits. The keys for each screen are listed at the bottom.

#### 2.1 Build

Three tabs:

- **Compile**: pick platforms and architectures, then press Build. Each build shows its progress and time, and Enter opens its log. The queue stops at the first failure.
- **Tools**: write `manifest.json` and `SHA256SUMS` for the built libraries, with the licence texts (Manifest), check them (Verify), and export the patched sources for `dart_smb2`'s bindings (Sources).
- **Docker**: see, build or delete the Docker images. The image a build needs is created automatically the first time, and again when `docker/Dockerfile` changes.

#### 2.2 Patches

The patch set applied to upstream libsmb2, read from `patches/libsmb2/`: one row per patch, with its scope (`shared` or `windows`) and the reason it exists, from the script's docstring.

---

### 3. Building

#### 3.1 macOS and iOS

On a Mac with Xcode:

```bash
./build macos          # universal xcframework
./build ios            # device and simulator xcframework
```

#### 3.2 Linux and Windows

Both build in Docker and run as your user, so `release_builds/` stays yours. Linux builds on Ubuntu 20.04, for the glibc 2.31 floor, and cross-compiles aarch64; Windows uses llvm-mingw for both architectures:

```bash
./build linux          # x86_64 and aarch64
./build windows        # x86_64 and arm64
```

#### 3.3 Android

Android builds on the host with the pinned NDK, found in the SDK folder or through `NDK_HOME` (or `ANDROID_NDK_HOME`, `ANDROID_NDK`). Another NDK version stops the build unless `ALLOW_ANY_NDK=1`. A `CC`, `CFLAGS` or other tool variable exported in the shell is ignored. Without the NDK the Android targets are greyed out, `./build all` skips them, and naming one fails.

```bash
./build android                  # all three ABIs
./build android-arm64-v8a        # one ABI
```

#### 3.4 From the command line

`./build` accepts targets as arguments and runs them in order, stopping at the first failure:

```bash
./build all            # everything this host can build; the rest is skipped
./build linux verify   # build Linux, then verify everything built
./build list           # every target
./build patches        # the patch set
./build help           # usage
```

`./build all` skips what this host cannot build with a line saying why (macOS and iOS off a Mac, Android without the NDK). It writes the manifest only when it skipped nothing, so a Linux machine never produces a `manifest.json` for part of a release; `write_manifest.sh` itself refuses anything but the nine libraries, and `ALLOW_PARTIAL=1 ./build manifest` writes one for a subset, with a warning. A target named explicitly that cannot run here is an error, and so is a group such as `android` none of whose targets can.

These variables are passed to the builds:

| Variable | Effect |
| :--- | :--- |
| `JOBS=N` | parallel compile jobs, all cores by default |
| `FORCE_DOWNLOAD=1` | download the libsmb2 and OpenSSL tarballs again |
| `KEEP_BUILD=1` | keep the build folders |
| `LIBSMB2_RELEASE=rN` and the other pins of `scripts/shared/_versions.sh`, `SOURCE_DATE_EPOCH` | override that pin, in the Docker builds as in the native ones |

#### 3.5 On GitHub Actions

Every push to a `release/` branch, and every pull request, runs `.github/workflows/build.yml`: it builds all nine libraries on GitHub's runners, Apple included (`macos-26`, with Xcode 26.6 pinned through `DEVELOPER_DIR`), collects them with `manifest.json`, `SHA256SUMS` and the licence texts in a `libsmb2-release` artifact, and checks them as in [4.3](#43-verifying) on an x86_64 and an arm64 runner, so both Linux libraries are also loaded on glibc 2.31. The macOS job loads the library it has built the same way. A `lint` job builds nothing: it runs `gofmt`, `go vet` and `go test` on the orchestrator, ShellCheck on the scripts, and `scripts/check_patches.sh`.

---

### 4. Using the binaries

#### 4.1 Installing into dart_smb2

From 0.2.0, `dart_smb2` gets libsmb2 through a build hook (`hook/build.dart`). When an app builds, the hook downloads the library for the target from the package's `libsmb2-rN` GitHub release and checks its SHA-256. To point the package at a release, run this in `dart_smb2`:

```bash
tool/update_libsmb2.sh r12                         # a published release
tool/update_libsmb2.sh r12 path/to/manifest.json   # before publishing it
```

It writes the release and the hashes from `manifest.json` into the hook.

#### 4.2 Local libraries in an app

To try a local build in an app, point the hook at `release_builds/` in the app's `pubspec.yaml`. The files are bundled as they are, without a checksum:

```yaml
hooks:
  user_defines:
    dart_smb2:
      libsmb2: path/to/libsmb2-scripts/release_builds
```

#### 4.3 Verifying

`./build verify` checks every library in `release_builds/` in the `verify` Docker image: that all nine are there and export every function in `verify/symbols.txt` (the ones `dart_smb2` binds), nothing outside `verify/exports.txt` (libsmb2's public API with the functions the patches add) and none of libcrypto's, that the licence texts of libsmb2 and OpenSSL are there and in both zips, that `SHA256SUMS` matches, the ELF or PE machine, that every library is stripped (no `.symtab` on ELF, no `.debug_*` section or COFF symbol on PE, no local symbol in a Mach-O slice), that the Linux and Android libraries are hardened (they import `__stack_chk_fail` and have full RELRO: a `GNU_RELRO` segment and `BIND_NOW`), the glibc 2.31 floor, the 16 KB alignment and libc-only dependencies on Android, the system-only imports on Windows, the slices and minimum OS on Apple, and the macOS framework symlinks. The library for the host's architecture is also loaded, its symbols resolved, `smb2_scripts_release()` checked to return `LIBSMB2_RELEASE`, and a context created and destroyed.

#### 4.4 Publishing a release

1. Build all nine libraries, usually by pushing a `release/` branch (see [3.5](#35-on-github-actions)).
2. In `dart_smb2`, run `tool/update_libsmb2.sh rN path/to/manifest.json` with the manifest of that Build, and push its own `release/` branch. While `libsmb2-rN` is not published, its CI finds the latest successful Build of rN by itself and tests its libraries (it needs the secret `LIBSMB2_SCRIPTS_TOKEN`; see `dart_smb2`'s `.github/workflows/ci.yml`).
3. Tag the commit `libsmb2-rN` in this repository.
4. Create the `libsmb2-rN` release on `dart_smb2` and upload the libraries, `COPYING`, `LICENCE-LGPL-2.1.txt`, `LICENSE-OpenSSL.txt`, `manifest.json` and `SHA256SUMS`, naming this repository's commit in its notes. From then on `dart_smb2`'s CI takes the published release.

---

### 5. How it works

`./build` is a small Go program ([Bubble Tea](https://github.com/charmbracelet/bubbletea)) that runs the shell scripts in `scripts/`, one per platform. Apple targets build with Xcode and Android with the NDK on the host; Linux, Windows and Verify run in a Docker image from `docker/Dockerfile`, which has one stage each.

Each build downloads the pinned tarballs and checks their SHA-256, extracts a fresh tree, installs the static `config.h` (`scripts/shared/config/`), applies the patches, builds a static libcrypto per architecture with OpenSSL's own `Configure` and `make` (a minimal one: no shared library, engines, legacy provider or algorithms libsmb2 never asks for), compiles `lib/*.c` (all of libsmb2 except the Kerberos wrapper) with `-O2 -fstack-protector-strong -D_FORTIFY_SOURCE=2` and one section per function and object, and links one library that exports `lib/libsmb2.syms`, with libcrypto inside; the Linux and Android links add `-z relro -z now` and `--no-undefined`. The link order is fixed (`LC_ALL=C`), so the same sources give the same bytes.

#### 5.1 The patch set

Every patch is a Python script with a docstring that says why it exists. It finds its place by exact text and stops the build when upstream has changed underneath it. The build applies them in alphabetical order, but none depends on that: any order gives the same tree. They all edit through `patches/_patchlib.py`: a patch writes nothing unless every one of its anchors matched the number of times it expects, and one run again on a tree it has already patched says so and leaves it alone. `scripts/check_patches.sh` checks all of that against the pinned tree without building a library, and compiles the files the patches touch with warnings on.

| Patch | Scope | What it does |
| :--- | :--- | :--- |
| `patch_compound_callbacks.py` | shared | calls every callback of a compound that times out before it is sent, so rmdir, unlink and the other path calls report the timeout |
| `patch_create_data_leaks.py` | shared | frees the call data of `unlink`, `mkdir`, `ftruncate`, `pread` and `pwrite` when their first request cannot be built |
| `patch_nterror_reporting.py` | shared | records the NT status on open and timeout failures |
| `patch_open_share_delete.py` | shared | adds `smb2_open2()`, whose `SMB2_OPEN_SHARE_DELETE` lets one open share delete, for the temporary files `dart_smb2` writes and renames into place: a handle the server keeps for a connection that died no longer blocks their rename or removal |
| `patch_poll_eintr.py` | shared | retries the sync API's `poll()` on `EINTR` |
| `patch_read_write_eof.py` | shared | makes `pread` and `pwrite` report 0 at end of file without reading the error reply as a read or write reply |
| `patch_rename_replace.py` | shared | adds `smb2_rename2()`, whose `SMB2_RENAME_REPLACE_IF_EXISTS` replaces an existing file in one step, behind `dart_smb2`'s `rename(..., overwrite: true)` |
| `patch_scripts_release.py` | shared | adds `smb2_scripts_release()`, which returns the release the library was built as (`LIBSMB2_RELEASE`, e.g. `"r12"`), so `dart_smb2` refuses a libsmb2 of another release or of upstream |
| `patch_rmdir_disposition.py` | shared | makes `rmdir` fail on a directory that is not empty |
| `patch_timestamps_before_epoch.py` | shared | gives a time before 1970, such as the 0 of a time the server does not keep, as 0 instead of a date far in the future |
| `patch_truncate_non_directory.py` | shared | makes `truncate` fail on a directory |
| `patch_unlink_non_directory.py` | shared | makes `unlink` fail on a directory, and so on a link to one (see below) |
| `patch_unlink_mkdir_status.py` | shared | makes `unlink` and `mkdir` report the first failure of their CREATE + CLOSE, with its NT status |
| `patch_utimes.py` | shared | adds `smb2_utimes()`, behind `dart_smb2`'s `setFileTimes` |
| `patch_windows_csprng.py` | windows | uses `BCryptGenRandom` for the client challenge, salt and nonce |
| `patch_windows_headers.py` | windows | builds with llvm-mingw's headers |
| `patch_windows_sockets.py` | windows | keeps 64-bit socket handles whole |

Links to directories: `unlink` opens the link itself (`FILE_OPEN_REPARSE_POINT`) and now asks for a non-directory, so on Windows a directory junction or directory symlink is no longer removed by `unlink`, which fails with `STATUS_FILE_IS_A_DIRECTORY`: remove it with `rmdir`, which removes the link and leaves its target alone. Samba follows symlinks on the server and libsmb2 does not negotiate the SMB3 POSIX extensions, so a Samba symlink to a directory cannot be removed over SMB2 at all (`unlink` fails as above, `rmdir` with `STATUS_DIRECTORY_NOT_EMPTY` or `STATUS_NOT_A_DIRECTORY`); a symlink to a file is still removed by `unlink`.

#### 5.2 Bumping upstream libsmb2

1. Set `LIBSMB2_COMMIT` and `LIBSMB2_TARBALL_SHA256` in `scripts/shared/_versions.sh`, and `LIBSMB2_RELEASE` to the next `rN`. OpenSSL is bumped the same way, with `OPENSSL_VERSION` and `OPENSSL_TARBALL_SHA256`; copy its `LICENSE.txt` to `licenses/openssl/` if it changed.
2. Build: every patch applies again to the new tree, and one whose anchor moved stops the build. Drop the patches upstream now carries. When upstream's `lib/libsmb2.syms` or a patch changes the exports, copy the patched tree's `lib/libsmb2.syms` (`KEEP_BUILD=1`) over the list in `verify/exports.txt`, or `./build verify` fails on the new ones.
3. Run `./build sources`, then `dart run tool/ffigen.dart` and `dart run tool/bindings_drift.dart` in `dart_smb2`.
4. Push a `release/` branch and publish as in [4.4](#44-publishing-a-release).

---

## Troubleshooting

- **"Go not found"**: install Go and run again.
- **A Linux, Windows or Verify run fails right away**: Docker isn't running.
- **macOS and iOS are greyed out**: they need a Mac with Xcode. GitHub Actions can build them instead.
- **The first Docker build is slow**: it is building the image; later builds reuse it until `docker/Dockerfile` changes.
- **"libsmb2 tarball SHA-256 mismatch"** or **"OpenSSL tarball SHA-256 mismatch"**: the cached download is stale or corrupt. Delete `sources/cache/` and build again.
- **A patch fails with "anchor found 0 time(s) instead of 1"**: upstream moved under the patch after a bump. Update the anchor in the named `patch_*.py`; `scripts/check_patches.sh` tries them all in a few seconds.
- **A patch fails with "already has the patch's sentinel"**: the text the patch recognises itself by is in the tree before it ran, so upstream now has it (drop or rework the patch) or another patch adds it.
- **"perl not found"** or **"make not found"** on Android: install them with the system's package manager; OpenSSL's `Configure` needs both.
- **"Android NDK 28.2.13676358 not found"** or **"the build is pinned to"**: install that NDK with the SDK Manager, set `NDK_HOME`, or build with `ALLOW_ANY_NDK=1`.
- **"N of the 9 release assets"** from the manifest: `release_builds/` lacks some libraries. Build them, take the CI artifact, or use `ALLOW_PARTIAL=1` for a manifest that is not a release.

---

## Licensing

- libsmb2's `lib/` and `include/` are licensed under the LGPL-2.1 or later; the texts are in [`licenses/libsmb2/`](licenses/libsmb2/). The code the patches add to libsmb2 is under the same terms.
- Each `libsmb2-rN` release, from r9, ships `COPYING` and `LICENCE-LGPL-2.1.txt` beside the binaries and inside the xcframework zips.
- From r11 every binary links OpenSSL's libcrypto statically, built from the unmodified release tarball. OpenSSL is licensed under the Apache License 2.0; its text is in [`licenses/openssl/`](licenses/openssl/), and each release ships it as `LICENSE-OpenSSL.txt` beside the binaries and under `licenses/openssl/` in the xcframework zips.
- Each `libsmb2-rN` release names, in its `manifest.json`, the commit of this repository it was built from: that commit, with the upstream tarballs it pins, is the corresponding source of the release's binaries.
- The scripts, the patch scripts themselves and the TUI are BSD-3-Clause, see [LICENSE](LICENSE).

---

## Project background

The build pipeline, the Go TUI and the patches for libsmb2 were written with Claude Code.

---

*Developed by Alessandro Di Ronza*
