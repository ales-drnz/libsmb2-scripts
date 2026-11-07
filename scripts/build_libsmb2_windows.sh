#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# build_libsmb2_windows.sh
#
# Cross-compiles libsmb2 into one DLL per architecture, from Linux, with the
# pinned OpenSSL's libcrypto built for each architecture and linked in
# statically.
#
# Output (release_builds/):
#   libsmb2_windows-x86_64.dll
#   libsmb2_windows-arm64.dll
#
# Target: Windows 10+ (x86_64, arm64), UCRT. Both architectures use the
# llvm-mingw toolchain installed by the `windows` stage of docker/Dockerfile
# (x86_64-w64-mingw32-clang, aarch64-w64-mingw32-clang), with perl and make
# for OpenSSL's Configure. libcrypto builds with OpenSSL's mingw64 target on
# x86_64; OpenSSL has no mingw target for arm64, so there it builds with
# scripts/shared/config/openssl-mingw-arm64.conf, in plain C (no-asm). The
# DLLs link the runtime statically and import only system DLLs (kernel32,
# ws2_32, bcrypt, user32, advapi32, the UCRT api sets). They are linked
# without a PE timestamp, so the same sources and toolchain give the same
# bytes, and stripped (-s: no DWARF from the static runtime, no COFF symbol
# table); the export table is kept.
#
# Usage (from the repo root): scripts/build_libsmb2_windows.sh
#
# Options (environment variables):
#   ARCHS=...         Comma-separated arch list (default: x86_64,arm64)
#   JOBS=N            Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1      Do not delete the intermediate build directory
#   FORCE_DOWNLOAD=1  Redownload the libsmb2 and OpenSSL tarballs even if cached
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-windows}"

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
PATCH_PLATFORM=windows prepare_libsmb2_sources "$BUILD_DIR"
prepare_openssl_sources "$BUILD_DIR"
libsmb2_sources
write_export_lists "$BUILD_DIR"

cc_for_arch() {
  case "$1" in
    x86_64) echo "x86_64-w64-mingw32-clang" ;;
    arm64)  echo "aarch64-w64-mingw32-clang" ;;
    *)      echo "" ;;
  esac
}

build_arch() {
  local arch="$1" cc
  cc="$(cc_for_arch "$arch")"
  [ -n "$cc" ] || { echo "error: unknown arch: $arch" >&2; exit 1; }
  command -v "$cc" >/dev/null || {
    echo "error: $cc not found (build inside the docker/Dockerfile windows stage)." >&2
    exit 1
  }

  local build="$BUILD_DIR/$arch" openssl_target
  rm -rf "$build"
  echo ""
  # OpenSSL's Configure target: mingw64 on x86_64; on arm64, where OpenSSL
  # has no mingw target, the one in openssl-mingw-arm64.conf, without
  # assembly. no-winstore drops the Windows certificate store loader, and
  # with it the import of crypt32.dll.
  case "$arch" in
    x86_64) openssl_target=(mingw64 no-winstore) ;;
    arm64)  openssl_target=(mingw-arm64 no-asm no-winstore
              "--config=$LIBSMB2_SCRIPTS_ROOT/scripts/shared/config/openssl-mingw-arm64.conf") ;;
  esac
  # llvm-mingw's binutils are LLVM's, under the target prefix too.
  CC="$cc" AR="${cc%-clang}-ar" RANLIB="${cc%-clang}-ranlib" RC="${cc%-clang}-windres" \
    build_libcrypto "$BUILD_DIR/openssl-$arch" "${openssl_target[@]}"

  echo "  Compiling $arch with $cc..."
  compile_objects "$build" "$cc" -- -D_WINDOWS -D_CRT_SECURE_NO_WARNINGS "${OPENSSL_INCLUDES[@]}"

  echo "  Linking $arch..."
  # libcrypto.a comes after the objects, so only what they use is linked;
  # the .def file exports libsmb2's API and nothing of libcrypto's. Its
  # system libraries follow it: bcrypt (its random source), user32 and
  # advapi32 (service detection and the event log of its fatal errors).
  "$cc" -shared -static -o "$build/libsmb2.dll" "$build"/*.o "$LIBCRYPTO" \
    "$BUILD_DIR/exports.def" \
    -Wl,--no-insert-timestamp \
    -Wl,--gc-sections \
    -s \
    -lws2_32 \
    -lbcrypt \
    -luser32 \
    -ladvapi32

  local output="$OUTPUT_DIR/libsmb2_windows-${arch}.dll"
  cp "$build/libsmb2.dll" "$output"
  echo "  Output: $output ($(du -h "$output" | cut -f1))"
}

echo "=== libsmb2: building for Windows ==="
echo "    Sources: ${#SOURCES[@]} files"
mkdir -p "$OUTPUT_DIR"

IFS=',' read -ra ARCH_LIST <<< "${ARCHS:-x86_64,arm64}"
for arch in "${ARCH_LIST[@]}"; do
  build_arch "$arch"
done

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_windows-*.dll"

if [ "${KEEP_BUILD:-0}" != "1" ]; then rm -rf "$BUILD_DIR"; fi
