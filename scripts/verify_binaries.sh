#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
#
# =============================================================================
# verify_binaries.sh
#
# Post-build sanity for the binaries in release_builds/ that are loadable on
# THIS host (Linux .so on Linux, macOS xcframework on macOS): dlopen each one
# and resolve every symbol the dart_smb2 FFI layer binds. Cross-compiled
# binaries for other OSes are listed but skipped.
#
# Usage:
#   ./scripts/verify_binaries.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"
VERIFY_DIR="$LIBSMB2_SCRIPTS_ROOT/verify"

TEST_BIN="$(mktemp -d)/dlopen_test"
trap 'rm -rf "$(dirname "$TEST_BIN")"' EXIT

HOST="$(uname -s)"
case "$HOST" in
  Linux)  cc -O0 "$VERIFY_DIR/dlopen_test.c" -o "$TEST_BIN" -ldl ;;
  Darwin) cc -O0 "$VERIFY_DIR/dlopen_test.c" -o "$TEST_BIN" ;;
  *) echo "verify: unsupported host $HOST" >&2; exit 1 ;;
esac

shopt -s nullglob
checked=0 skipped=0 failed=0

for f in "$OUTPUT_DIR"/*; do
  base="$(basename "$f")"
  case "$HOST:$base" in
    Linux:libsmb2_linux-x86_64.so)
      if "$TEST_BIN" "$f"; then checked=$((checked+1)); else failed=$((failed+1)); fi ;;
    Linux:libsmb2_linux-aarch64.so)
      if [ "$(uname -m)" = "aarch64" ]; then
        if "$TEST_BIN" "$f"; then checked=$((checked+1)); else failed=$((failed+1)); fi
      else
        echo "SKIP $base (aarch64 binary on $(uname -m) host)"; skipped=$((skipped+1))
      fi ;;
    Darwin:libsmb2_macos.xcframework.zip)
      tmp="$(mktemp -d)"
      unzip -q "$f" -d "$tmp"
      dylib="$(find "$tmp" -path "*macos*" -name libsmb2 -type f | head -1)"
      if [ -n "$dylib" ] && "$TEST_BIN" "$dylib"; then
        checked=$((checked+1))
      else
        echo "FAIL $base"; failed=$((failed+1))
      fi
      rm -rf "$tmp" ;;
    *)
      echo "SKIP $base (not loadable on $HOST)"; skipped=$((skipped+1)) ;;
  esac
done

echo ""
echo "verify: $checked ok, $skipped skipped, $failed failed"
[ "$failed" -eq 0 ]
