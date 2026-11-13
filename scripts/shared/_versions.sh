# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Pinned upstream versions — single source of truth across the 5
# build_libsmb2_<platform>.sh scripts.
#
# This file is sourced by every per-platform build script. Do not run
# it directly.

# ── libsmb2 ──────────────────────────────────────────────────────────────────
# Pinned to upstream master at 2026-11-07 (libsmb2-6.2-606-ga52c157). Since
# r10 (4d9ce67) upstream fixed, on the client side: zero-length reads and
# writes, which failed (30fa5ae) and now keep a CreditCharge of 1 (aa8299d),
# the format of a copychunk error reply, now told by its size (14f3bd7),
# and the encoding and decoding of lease and oplock breaks and their
# acknowledgements (a52c157, a32e704, 497e707, 7a1f7b4). None of the local
# patches is carried upstream yet.
#
# OpenSSL is on (HAVE_OPENSSL in config.h): libsmb2 signs and seals through
# libcrypto, and offers AES-256-GCM and AES-128-GCM ahead of AES-128-CCM on
# SMB 3.1.1. libcrypto is built from the pinned tarball below and linked
# statically into each library, whose export list keeps its symbols
# private. QUIC and SMB Direct (lib/quic.c, lib/smbdirect.c) stay off: their
# sources compile to nothing without HAVE_LIBQUIC / HAVE_LIBRDMACM.
#
# Share enumeration is upstream's self-contained flat API
# (include/smb2/libsmb2-share-enum.h, lib/smb2-share-enum.c); the full
# DCE/RPC stack is the separate libdcerpc project and is not built here.
#
# On bump: update LIBSMB2_COMMIT + LIBSMB2_TARBALL_SHA256 (sha256sum of the
# GitHub codeload tarball), re-run every patch (they fail loudly if an anchor
# drifted), and rebuild all platforms.
export LIBSMB2_COMMIT="${LIBSMB2_COMMIT:-a52c1571a1ff223bde5bb3df9fec7af5ce3855d4}"
export LIBSMB2_TARBALL_SHA256="${LIBSMB2_TARBALL_SHA256:-c150c934c1353f1f903261c8c51cd605cd3f59beff1e4619240cf059729f18fb}"

# Human-readable marker of what the commit is (informational only —
# the commit hash above is what the build actually uses).
export LIBSMB2_VERSION="${LIBSMB2_VERSION:-7.0.0-dev+git20261107.a52c157}"

# Numeric form for Apple bundle versions (CFBundleShortVersionString):
# `git describe` of the pin is libsmb2-6.2-606-ga52c157.
export LIBSMB2_BUNDLE_VERSION="${LIBSMB2_BUNDLE_VERSION:-6.2.606}"

# ── OpenSSL ──────────────────────────────────────────────────────────────────
# libcrypto for libsmb2's signing and sealing (AES-128/256-GCM, AES-128-CCM,
# AES-CMAC, HMAC-SHA256). 3.5 is the LTS branch (supported to 2030-04); the
# tarball is the one GitHub serves for the openssl-<version> release, checked
# against the SHA-256 OpenSSL publishes beside it. Apache-2.0: its LICENSE.txt
# ships with the binaries (licenses/openssl/).
export OPENSSL_VERSION="${OPENSSL_VERSION:-3.5.9}"
export OPENSSL_TARBALL_SHA256="${OPENSSL_TARBALL_SHA256:-603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a}"

# ── Android NDK ──────────────────────────────────────────────────────────────
# The NDK build_libsmb2_android.sh builds with, kept equal to Flutter's
# default (flutter.ndkVersion); 28.2.13676358 is r28c. The one place that
# names it: the script, the orchestrator (tui/targets.go) and the CI
# workflow, which installs it, all read it here.
export NDK_VERSION="${NDK_VERSION:-28.2.13676358}"

# ── Release ──────────────────────────────────────────────────────────────────
# Tag suffix of the GitHub release the binaries are published under
# (libsmb2-<release> on github.com/ales-drnz/dart_smb2). Recorded in
# manifest.json, and baked into every library by patch_scripts_release.py:
# smb2_scripts_release() returns it ("r11"), and dart_smb2 refuses a libsmb2
# that names another release.
export LIBSMB2_RELEASE="${LIBSMB2_RELEASE:-r11}"
