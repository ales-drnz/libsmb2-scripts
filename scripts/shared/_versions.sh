# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Pinned upstream versions — single source of truth across the 5
# build_libsmb2_<platform>.sh scripts.
#
# This file is sourced by every per-platform build script. Do not run
# it directly.

# ── libsmb2 ──────────────────────────────────────────────────────────────────
# Pinned to upstream master at 2026-11-05 (libsmb2-6.2-596-g4d9ce67). Since
# r9 (e94eee9) upstream fixed, on the client side: an out of bounds read in
# NTOWFv2 with an empty user on 32-bit (2832fb4), uninitialised heap in the
# NTLM AUTHENTICATE (3f62685), a PDU sent in the clear on a sealed session
# (bd10fea, b78e01f), READ replies longer than asked for (6cd18a5), replies
# whose command differs from their request (e50ff7e), payload bounds and
# zeroing in the decoders (3c7bd04, 4c5d08d), and a sync call leaking its
# state when the connection fails mid-call (ee56559). It also took over
# three local patches: client contexts stay off the active list (565460d),
# a callback that closed the connection keeps its error (e7beeb4), and
# smb2_destroy_context() calls every callback of an unsent compound
# (ee56559, b4a409e).
#
# QUIC, SMB Direct and OpenSSL (lib/quic.c, lib/smbdirect.c, HAVE_OPENSSL)
# are off: their sources compile to nothing without HAVE_LIBQUIC /
# HAVE_LIBRDMACM, and sealing keeps the built-in AES-128-CCM.
#
# Share enumeration is upstream's self-contained flat API
# (include/smb2/libsmb2-share-enum.h, lib/smb2-share-enum.c); the full
# DCE/RPC stack is the separate libdcerpc project and is not built here.
#
# On bump: update LIBSMB2_COMMIT + LIBSMB2_TARBALL_SHA256 (sha256sum of the
# GitHub codeload tarball), re-run every patch (they fail loudly if an anchor
# drifted), and rebuild all platforms.
export LIBSMB2_COMMIT="${LIBSMB2_COMMIT:-4d9ce67863332462236d86bf76c85617a0b2897d}"
export LIBSMB2_TARBALL_SHA256="${LIBSMB2_TARBALL_SHA256:-6c34870b2aef319b5415e9912b406f922e03f127c072764ceca78139e6d94b7a}"

# Human-readable marker of what the commit is (informational only —
# the commit hash above is what the build actually uses).
export LIBSMB2_VERSION="${LIBSMB2_VERSION:-7.0.0-dev+git20261105.4d9ce67}"

# Numeric form for Apple bundle versions (CFBundleShortVersionString):
# `git describe` of the pin is libsmb2-6.2-596-g4d9ce67.
export LIBSMB2_BUNDLE_VERSION="${LIBSMB2_BUNDLE_VERSION:-6.2.596}"

# ── Release ──────────────────────────────────────────────────────────────────
# Tag suffix of the GitHub release the binaries are published under
# (libsmb2-<release> on github.com/ales-drnz/dart_smb2). Recorded in
# manifest.json.
export LIBSMB2_RELEASE="${LIBSMB2_RELEASE:-r10}"
