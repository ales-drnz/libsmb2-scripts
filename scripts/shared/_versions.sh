# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Pinned upstream versions — single source of truth across the 5
# build_libsmb2_<platform>.sh scripts.
#
# This file is sourced by every per-platform build script. Do not run
# it directly.

# ── libsmb2 ──────────────────────────────────────────────────────────────────
# Pinned to upstream master at 2026-11-20 (libsmb2-7.0.0-25-gc7996bb):
# the libsmb2-7.0.0 release, the first from master since 6.2, and after it
# the bounds on negotiated I/O sizes and reply lengths (69f5941, which stops
# a server that negotiates a read size of 0 from writing past the caller's
# buffer), signing across partial reads (9486279) and stat results kept
# alive after a failed wait (c94a9e1). Since the previous pin (a52c157)
# upstream took six of the local patches, as the commits sent from here
# (1882fd7, 702558e, a0ceca2, 62367d5, 6dfddd9) and as the reference-
# counted compound callbacks of #516, and replaced a seventh (timestamps
# before 1970 are now negative seconds, 177a9de). Those patches are gone;
# nterror_reporting and unlink_mkdir_status keep only what upstream does
# not do yet.
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
export LIBSMB2_COMMIT="${LIBSMB2_COMMIT:-c7996bb97601a7f04d3e5c371317425da9b82ba4}"
export LIBSMB2_TARBALL_SHA256="${LIBSMB2_TARBALL_SHA256:-1208fe411700e6cfab41e843d18de3398dccd77390cc9c964e81353213c34685}"

# Human-readable marker of what the commit is (informational only —
# the commit hash above is what the build actually uses).
export LIBSMB2_VERSION="${LIBSMB2_VERSION:-7.0.0+git20261120.c7996bb}"

# Numeric form for Apple bundle versions (CFBundleShortVersionString):
# `git describe` of the pin is libsmb2-7.0.0-25-gc7996bb.
export LIBSMB2_BUNDLE_VERSION="${LIBSMB2_BUNDLE_VERSION:-7.0.25}"

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
# smb2_scripts_release() returns it ("r14"), and dart_smb2 refuses a libsmb2
# that names another release.
export LIBSMB2_RELEASE="${LIBSMB2_RELEASE:-r14}"
