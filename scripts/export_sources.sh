#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
#
# =============================================================================
# export_sources.sh
#
# Materializes the pinned + patched libsmb2 tree at a stable path so tooling
# outside the build can read its headers. dart_smb2's ffigen.yaml points here:
# the bindings MUST be generated from the patched headers, because the shared
# patches add public API (patch_utimes.py adds smb2_utimes/smb2_utimes_async
# to include/smb2/libsmb2.h) that upstream does not have.
#
# Only the shared patches are applied — no platform overlay. The overlays are
# compile fixes for one toolchain (see patches/libsmb2/windows/), not ABI
# changes, so the shared tree is the correct basis for bindings that have to
# describe every platform.
#
# Output: sources/libsmb2-src/ (gitignored; re-created on every run)
#
# Usage:
#   ./scripts/export_sources.sh
#   ./build sources
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"

echo "=== libsmb2: exporting patched sources ==="

# PATCH_PLATFORM deliberately unset -> shared patches only.
prepare_libsmb2_sources "$LIBSMB2_SCRIPTS_ROOT/sources"

echo ""
echo "Patched sources at: $SMB2_SRC"
echo "libsmb2 pin:        ${LIBSMB2_COMMIT:0:12} (${LIBSMB2_VERSION})"
echo ""
echo "Regenerate the Dart bindings with:"
echo "  cd ../dart_smb2 && dart run ffigen --config ffigen.yaml"
