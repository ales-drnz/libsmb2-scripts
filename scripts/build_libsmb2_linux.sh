#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# build_libsmb2_linux.sh
#
# Fetches the pinned libsmb2 source, applies the patch set, and compiles it
# into one shared library per architecture.
#
# Output (release_builds/):
#   libsmb2_linux-x86_64.so
#   libsmb2_linux-aarch64.so
#
# Target: Linux with glibc 2.31 or newer (Ubuntu 20.04, Debian 11 and
# later). Build inside the `linux` stage of docker/Dockerfile (ubuntu:20.04),
# so no binary references a newer glibc symbol; `./build verify` checks it.
#
# Compilers: gcc (x86_64) and aarch64-linux-gnu-gcc (aarch64 cross).
#
# Usage (from the repo root): scripts/build_libsmb2_linux.sh
#
# Options (environment variables):
#   ARCHS=...         Comma-separated arch list (default: x86_64,aarch64)
#   JOBS=N            Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1      Do not delete the intermediate build directory
#   FORCE_DOWNLOAD=1  Redownload the libsmb2 tarball even if cached
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-linux}"

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
prepare_libsmb2_sources "$BUILD_DIR"
libsmb2_sources
write_export_lists "$BUILD_DIR"

cc_for_arch() {
  case "$1" in
    x86_64)  echo "gcc" ;;
    aarch64) echo "aarch64-linux-gnu-gcc" ;;
    *)       echo "" ;;
  esac
}

build_arch() {
  local arch="$1" cc
  cc="$(cc_for_arch "$arch")"
  [ -n "$cc" ] || { echo "error: unknown arch: $arch" >&2; exit 1; }
  command -v "$cc" >/dev/null || {
    echo "error: $cc not found (build inside the docker/Dockerfile linux stage)." >&2
    exit 1
  }

  local build="$BUILD_DIR/$arch"
  rm -rf "$build"
  echo ""
  echo "  Compiling $arch with $cc..."
  compile_objects "$build" "$cc" --

  echo "  Linking $arch..."
  # No SONAME: consumers rename the file when they bundle it, and the
  # loader then knows it by that name. -s drops the static symbol table;
  # the exported API lives in .dynsym, which stays.
  "$cc" -shared -s -o "$build/libsmb2.so" "$build"/*.o \
    -Wl,--version-script="$BUILD_DIR/exports.ver" \
    -Wl,--build-id=none \
    -pthread

  local output="$OUTPUT_DIR/libsmb2_linux-${arch}.so"
  cp "$build/libsmb2.so" "$output"
  echo "  Output: $output ($(du -h "$output" | cut -f1))"
}

echo "=== libsmb2: building for Linux ==="
echo "    Sources: ${#SOURCES[@]} files"
mkdir -p "$OUTPUT_DIR"

IFS=',' read -ra ARCH_LIST <<< "${ARCHS:-x86_64,aarch64}"
for arch in "${ARCH_LIST[@]}"; do
  build_arch "$arch"
done

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_linux-*.so"

if [ "${KEEP_BUILD:-0}" != "1" ]; then rm -rf "$BUILD_DIR"; fi
