# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Pinned upstream versions — single source of truth across the 5
# build_libsmb2_<platform>.sh scripts.
#
# This file is sourced by every per-platform build script. Do not run
# it directly.

# ── libsmb2 ──────────────────────────────────────────────────────────────────
# Pinned to upstream master at 2026-08-14 (post-6.2). This snapshot carries
# the August 2026 security hardening series: mandatory signature verification
# when the connection is signed, bounds validation across every PDU decoder,
# the ntlmssp out-of-bounds fix, a CSPRNG for client challenge / preauth salt
# / CCM nonce, and rejection of never-offered negotiated dialects.
#
# The full DCE/RPC stack lives in upstream's separate libdcerpc/ tree and is
# NOT built here — the minimal in-core path (lib/libsmb2-dcerpc*.c +
# lib/smb2-share-enum.c) covers the share enumeration the wrapper needs.
#
# On bump: update LIBSMB2_COMMIT + LIBSMB2_TARBALL_SHA256 (sha256sum of the
# GitHub codeload tarball), re-run every patch (they fail loudly if an anchor
# drifted), and rebuild all platforms.
export LIBSMB2_COMMIT="${LIBSMB2_COMMIT:-595d128b4d11a88a335eee961689a157e4f76cd3}"
export LIBSMB2_TARBALL_SHA256="${LIBSMB2_TARBALL_SHA256:-b4e3fe3890655dce283a39caf47a0a4adf1e0a5ab1a6a33235e5cabcdb336249}"

# Human-readable marker of what the commit is (informational only —
# the commit hash above is what the build actually uses).
export LIBSMB2_VERSION="${LIBSMB2_VERSION:-6.1.0+git20260814}"
