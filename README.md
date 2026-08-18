# libsmb2-scripts

#### Patched libsmb2, built for every platform.

[![](https://img.shields.io/badge/libsmb2--scripts-0.1.2-7DCFFF.svg?style=for-the-badge)](CHANGELOG.md)
[![](https://img.shields.io/badge/libsmb2-master%202026--08--14-orange.svg?style=for-the-badge)](https://github.com/sahlberg/libsmb2)
[![](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg?style=for-the-badge)](LICENSE)
[![](https://img.shields.io/github/stars/ales-drnz/libsmb2-scripts?style=for-the-badge&logo=github&logoColor=white)](https://github.com/ales-drnz/libsmb2-scripts)
[![](https://img.shields.io/discord/1485588004029333516?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/g2Qf4Mq9MP)
[![](https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/cw/ales_drnz)
[![](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/ales.drnz)

This repo builds the **SMB engine** behind the [`dart_smb2`](https://pub.dev/packages/dart_smb2) Flutter package: a pinned upstream [libsmb2](https://github.com/sahlberg/libsmb2) plus a small, documented patch set, cross-compiled for every platform: macOS, iOS, Android, Windows and Linux. You drive everything from **one command**, `./build`, a friendly menu where you pick what to build and watch it happen.

It is also the **corresponding-source offer** for the LGPL-2.1 libsmb2 binaries shipped with `dart_smb2`: the exact upstream commit is pinned in [`scripts/shared/_versions.sh`](scripts/shared/_versions.sh) and every modification is a standalone, reviewable patch under [`patches/libsmb2/`](patches/libsmb2/).

---

## Quick start

Clone this repo **next to** the Flutter package, then run the menu:

```bash
git clone https://github.com/ales-drnz/libsmb2-scripts
git clone https://github.com/ales-drnz/dart_smb2       # sibling folder

cd libsmb2-scripts
./build                # opens the menu: pick targets, press Build
```

On Windows run `build.cmd` instead. The first run fetches the Go dependencies automatically; the first Docker build also builds the build-env image once before compiling.

---

## What it produces

One `libsmb2` per platform and architecture, dropped into `release_builds/`:

| Platform | Architectures | Output |
| :--- | :--- | :--- |
| **macOS** | arm64, x86_64 (universal) | `libsmb2_macos.xcframework.zip` |
| **iOS** | arm64 (device + sim), x86_64 (sim) | `libsmb2_ios.xcframework.zip` |
| **Android** | arm64-v8a, armeabi-v7a, x86_64 | `libsmb2_android-<abi>.so` |
| **Linux** | x86_64, aarch64 | `libsmb2_linux-<arch>.so` |
| **Windows** | x86_64, arm64 | `libsmb2_windows-<arch>.dll` |

Each binary statically links the patched libsmb2 into the `smb2_wrapper.c` shared library that `dart_smb2` binds over FFI. The exact pinned libsmb2 commit lives in `scripts/shared/_versions.sh`, and the patch set is browsable from the **Patches** tab (or `./build patches`).

---

## Contents

*   [Quick start](#quick-start)
*   [Guide](#guide)
    <details>
    <summary><a href="#1-prerequisites"><b>1. Prerequisites</b></a></summary>

    * [1.1 Required tools](#11-required-tools)
    * [1.2 Which host builds what](#12-which-host-builds-what)

    </details>

    <details>
    <summary><a href="#2-setup"><b>2. Setup</b></a></summary>

    * [2.1 Folder layout](#21-folder-layout)
    * [2.2 Run it](#22-run-it)

    </details>

    <details>
    <summary><a href="#3-using-the-menu"><b>3. Using the menu</b></a></summary>

    * [3.1 Build tab](#31-build-tab)
    * [3.2 Patches tab](#32-patches-tab)

    </details>

    <details>
    <summary><a href="#4-building-for-each-platform"><b>4. Building for each platform</b></a></summary>

    * [4.1 macOS and iOS](#41-macos-and-ios)
    * [4.2 Linux and Windows](#42-linux-and-windows)
    * [4.3 Android](#43-android)
    * [4.4 Everything at once](#44-everything-at-once)

    </details>

    <details>
    <summary><a href="#5-command-line"><b>5. Command line</b></a></summary>

    * [5.1 Targets and chaining](#51-targets-and-chaining)
    * [5.2 Build knobs](#52-build-knobs)

    </details>

    <details>
    <summary><a href="#6-output-and-verification"><b>6. Output and verification</b></a></summary>

    * [6.1 Where results go](#61-where-results-go)
    * [6.2 Installing into dart_smb2](#62-installing-into-dart_smb2)
    * [6.3 Verifying the binaries](#63-verifying-the-binaries)

    </details>

    <details>
    <summary><a href="#7-how-it-works"><b>7. How it works</b></a></summary>

    * [7.1 The build pipeline](#71-the-build-pipeline)
    * [7.2 The patch set](#72-the-patch-set)
    * [7.3 Bumping upstream libsmb2](#73-bumping-upstream-libsmb2)

    </details>
*   [Troubleshooting](#troubleshooting)
*   [Licensing](#licensing)
*   [Project background](#project-background)

---

## Guide

### 1. Prerequisites

You only need the tools for the platforms you actually build. Linux and Windows binaries cross-compile inside one Docker image, so the host CPU architecture doesn't matter for those.

#### 1.1 Required tools

| Tool | Needed for | Install |
| :--- | :--- | :--- |
| **Go** | always, it runs the `./build` menu | `brew install go` / `pacman -S go` (or [go.dev/dl](https://go.dev/dl/)) |
| **Docker** | Linux and Windows builds | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or the docker engine, just have it running |
| **Xcode** | macOS and iOS builds (macOS host only) | Mac App Store |
| **Android NDK** | Android builds (pinned `28.2.13676358`) | Android Studio SDK Manager, or set `NDK_HOME` |
| python3 + curl | always (fetch + patch step) | preinstalled almost everywhere |

#### 1.2 Which host builds what

| Host | Can build |
| :--- | :--- |
| **macOS** | *everything*: Apple targets via Xcode, Android via the NDK, the rest via Docker |
| **Linux** | everything **except** macOS and iOS (those need a Mac) |
| **Windows** | Linux and Windows targets via Docker: use `build.cmd` instead of `./build` |

---

### 2. Setup

#### 2.1 Folder layout

The builder installs its results **into** the `dart_smb2` package, so it expects to find it **next to** this repo:

```
your-projects/
├── libsmb2-scripts/    ← this repo
└── dart_smb2/          ← the Flutter package (clone it here)
```

> Folder somewhere else? Point to it with
> `DART_SMB2_ROOT=/path/to/dart_smb2 ./build`.

#### 2.2 Run it

```bash
cd libsmb2-scripts
./build
```

On Windows, run `build.cmd` instead. The first run fetches the Go dependencies automatically; the first Docker build also builds the build-env image (once) before compiling.

---

### 3. Using the menu

Move with the **arrow keys**, toggle a target with **Space**, then go to the **Build** button and press **Enter** to start. Every screen shows its keyboard shortcuts along the bottom.

#### 3.1 Build tab

All targets, grouped by OS, plus the **Tools** row (Checksums, Verify). While a queue runs you get one row per target with a live tick/spinner and a scrolling log tail; the queue stops at the first failure, like `make`.

#### 3.2 Patches tab

The patch set applied to upstream libsmb2, read live from `patches/libsmb2/` — one row per patch with its scope (`shared` / `windows`) and, for the focused patch, the full rationale from the script's docstring. What you see here is exactly what the build applies: the catalog can't drift from the code.

---

### 4. Building for each platform

#### 4.1 macOS and iOS

Native builds against Xcode (macOS host only). Each produces a zipped dynamic `libsmb2.xcframework` — universal arm64 + x86_64 for macOS; device arm64 + simulator arm64/x86_64 for iOS.

```bash
./build macos ios
```

#### 4.2 Linux and Windows

Cross-compiled inside the `libsmb2-builder` Docker image (gcc + aarch64 cross for Linux; MinGW-w64 + LLVM-MinGW for Windows). Works from any host with Docker running; the image is built automatically the first time.

```bash
./build linux windows      # or: desktop-all
```

#### 4.3 Android

Native NDK build on the host (macOS or Linux) for all three ABIs. The NDK version is pinned to Flutter's default (`28.2.13676358`) — install it via the SDK Manager or point `NDK_HOME` at any NDK root.

```bash
./build android            # or one ABI: android-armeabi-v7a
```

#### 4.4 Everything at once

```bash
./build all                # macos + ios + android + desktop-all + checksums
```

---

### 5. Command line

#### 5.1 Targets and chaining

Any menu target works headlessly, and they chain left to right, stopping at the first failure:

```bash
./build linux windows      # desktop cross builds
./build macos verify       # build macOS, then verify
./build list               # every target and whether it can run here
./build patches            # the patch set, one line each
```

#### 5.2 Build knobs

Environment variables, forwarded into Docker builds:

| Knob | Effect |
| :--- | :--- |
| `JOBS=N` | parallel compile jobs (default: all cores) |
| `KEEP_BUILD=1` | keep the intermediate build tree |
| `FORCE_DOWNLOAD=1` | redownload the pinned libsmb2 tarball even if cached |

---

### 6. Output and verification

#### 6.1 Where results go

Build scripts emit **only** to `release_builds/` (gitignored). Nothing touches the consumer package until you run Checksums.

#### 6.2 Installing into dart_smb2

`./build checksums` is the single point that installs artifacts into the sibling `dart_smb2/`:

| Platform | Destination |
| :--- | :--- |
| Android | `dart_smb2/android/src/main/jniLibs/<abi>/libsmb2.so` |
| iOS | `dart_smb2/ios/dart_smb2/Frameworks/libsmb2.xcframework/` |
| macOS | `dart_smb2/macos/dart_smb2/Frameworks/libsmb2.xcframework/` |
| Linux | `dart_smb2/linux/libs/<arch>/libsmb2.so` |
| Windows | `dart_smb2/windows/libs/<arch>/libsmb2.dll` |

Plus the matching SHA-256 written into `build.gradle.kts`, `CMakeLists.txt`, the podspec and `Package.swift` for every consumer.

#### 6.3 Verifying the binaries

`./build verify` dlopens every binary loadable on the current host and resolves the **complete FFI symbol surface** `dart_smb2` binds — the `smb2w_*` wrapper API plus the patched-in `smb2_utimes` family. Cross-compiled binaries for other OSes are listed and skipped.

---

### 7. How it works

`./build` is a small Go ([Bubble Tea](https://github.com/charmbracelet/bubbletea)) TUI that orchestrates the per-platform shell scripts in `scripts/`, with no Makefile in the loop.

#### 7.1 The build pipeline

Every `build_libsmb2_<platform>.sh` follows the same three steps:

1. **Fetch** — download the pinned libsmb2 tarball (commit + SHA-256 from `scripts/shared/_versions.sh`) into `sources/cache/`, once.
2. **Patch** — extract a fresh tree per build, install the static `config.h` (`scripts/shared/config/`), and run every `patches/libsmb2/shared/patch_*.py` plus the platform overlay (`windows/`).
3. **Compile** — build all of `lib/*.c` (minus the Kerberos wrapper; upstream's full DCE/RPC stack stays out — the in-core minimal path covers share enumeration) + `src/smb2_wrapper.c` per arch, and link one shared library.

#### 7.2 The patch set

Each patch is a standalone Python script with a docstring explaining *why* it exists. Patches use exact string anchors and **fail loudly** when upstream drifts underneath them — a failed patch is a build failure, never a silent skip.

#### 7.3 Bumping upstream libsmb2

1. Edit `LIBSMB2_COMMIT` (+ tarball SHA-256) in `scripts/shared/_versions.sh`.
2. Run any build — every patch re-applies against the new tree; fix any patch whose anchor drifted.
3. `./build all` + `./build verify`, then edit `LIB_VERSION` / `RELEASE_VERSION` in `scripts/bump_version.sh`, run `./build bump`, and cut a `libsmb2-rN` GitHub release from `release_builds/`.

---

## Troubleshooting

- **"Go not found"** → install Go (`brew install go` / `pacman -S go`) and re-run.
- **Linux or Windows build fails immediately** → make sure **Docker is running**.
- **macOS or iOS options are greyed out** → those need a **Mac with Xcode**; they can't be built on Windows or Linux.
- **"cannot locate dart_smb2"** → clone `dart_smb2` next to this folder, or set `DART_SMB2_ROOT` (see [§2.1](#21-folder-layout)).
- **"libsmb2 tarball SHA-256 mismatch"** → the cached download is stale or corrupt: delete `sources/cache/` and retry (after a commit bump, update `LIBSMB2_TARBALL_SHA256` too).
- **A patch fails with "anchor not found"** → upstream moved under the patch after a commit bump; open the named `patch_*.py` and update its anchor.
- **Android: "Android NDK not found"** → install NDK `28.2.13676358` via the SDK Manager, or set `NDK_HOME`.

---

## Licensing

- **libsmb2** is LGPL-2.1 (with some BSD-licensed files). The patches in `patches/libsmb2/` modify it and are provided under the same terms; this public repo with its pinned upstream commit constitutes the corresponding source for the libsmb2 binaries shipped in `dart_smb2` releases.
- The build infrastructure itself (scripts, TUI, and the first-party wrapper `src/smb2_wrapper.c`) is BSD-3-Clause — see [LICENSE](LICENSE).

---

## Project background

The build pipeline, the Go TUI and the patches for libsmb2 were implemented through the use of Claude Code.

---

*Developed by Alessandro Di Ronza*
