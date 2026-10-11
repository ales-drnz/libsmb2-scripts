# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Pinned upstream versions — single source of truth across the 5
# build_libsmb2_<platform>.sh scripts.
#
# This file is sourced by every per-platform build script. Do not run
# it directly.

# ── libsmb2 ──────────────────────────────────────────────────────────────────
# Pinned to upstream master at 2026-10-11 (libsmb2-6.2-407-ge94eee9). On top
# of the August 2026 hardening series this snapshot enforces sealed replies,
# validates transform headers and caps receive lengths (e94eee9), fixes the
# unaligned SessionId store in smb3-seal (6991d46), and carries the two
# fixes that used to be local patches: the timeout sweep respecting
# caller_frees_pdu (b0b1e42) and the smb2_open() sync_cb_data leak (7905719).
#
# Share enumeration is upstream's self-contained flat API
# (include/smb2/libsmb2-share-enum.h, lib/smb2-share-enum.c); the full
# DCE/RPC stack is the separate libdcerpc project and is not built here.
#
# On bump: update LIBSMB2_COMMIT + LIBSMB2_TARBALL_SHA256 (sha256sum of the
# GitHub codeload tarball), re-run every patch (they fail loudly if an anchor
# drifted), and rebuild all platforms.
export LIBSMB2_COMMIT="${LIBSMB2_COMMIT:-e94eee9465d55ed094ace2c038a8705b4822dada}"
export LIBSMB2_TARBALL_SHA256="${LIBSMB2_TARBALL_SHA256:-7f347c08c8cb66a94e42d1cac4686e71a093a7022e7e77cb5cc9325b8369b0ce}"

# Human-readable marker of what the commit is (informational only —
# the commit hash above is what the build actually uses).
export LIBSMB2_VERSION="${LIBSMB2_VERSION:-7.0.0-dev+git20261011.e94eee9}"

# Numeric form for Apple bundle versions (CFBundleShortVersionString):
# `git describe` of the pin is libsmb2-6.2-407-ge94eee9.
export LIBSMB2_BUNDLE_VERSION="${LIBSMB2_BUNDLE_VERSION:-6.2.407}"

# ── Release ──────────────────────────────────────────────────────────────────
# Tag suffix of the GitHub release the binaries are published under
# (libsmb2-<release> on github.com/ales-drnz/dart_smb2). Recorded in
# manifest.json.
export LIBSMB2_RELEASE="${LIBSMB2_RELEASE:-r9}"
