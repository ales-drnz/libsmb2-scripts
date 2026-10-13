#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# build_libsmb2_android.sh
#
# Cross-compiles libsmb2 into one shared library per Android ABI.
#
# Output (release_builds/):
#   libsmb2_android-arm64-v8a.so
#   libsmb2_android-armeabi-v7a.so
#   libsmb2_android-x86_64.so
#
# Target: Android 7.0+ (API 24). The 64-bit ABIs are linked with 16 KB
# segment alignment (NDK r28 default), which Android 15+ devices with 16 KB
# pages require.
#
# Usage (from the repo root): NDK_HOME=/path/to/ndk scripts/build_libsmb2_android.sh
#
# Options (environment variables):
#   NDK_HOME=...       Android NDK root (also ANDROID_NDK_HOME / ANDROID_NDK)
#   NDK_VERSION=...    Pinned NDK version (default: 28.2.13676358 = r28c)
#   ALLOW_ANY_NDK=1    Build with another NDK when the pinned one is missing
#   ANDROID_API=24     Minimum API level (default and floor: 24)
#   ABIS=...           Comma-separated ABI list (default: arm64-v8a,armeabi-v7a,x86_64)
#   JOBS=N             Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1       Do not delete the intermediate build directory
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-android}"

API="${ANDROID_API:-24}"
if ! [[ "$API" =~ ^[0-9]+$ ]] || (( API < 24 )); then
  echo "ERROR: ANDROID_API must be >= 24 (got '$API'). Android 7.0+ is the supported floor." >&2
  exit 1
fi

# Pinned NDK, kept equal to Flutter's default (flutter.ndkVersion).
NDK_VERSION="${NDK_VERSION:-28.2.13676358}"

# ── Locate the NDK ───────────────────────────────────────────────────────────

NDK="${NDK_HOME:-${ANDROID_NDK_HOME:-${ANDROID_NDK:-}}}"
if [ -z "$NDK" ]; then
  for d in \
    "$HOME/Library/Android/sdk/ndk/$NDK_VERSION" \
    "$HOME/Android/Sdk/ndk/$NDK_VERSION" \
    "/opt/android-ndk-$NDK_VERSION" \
    "/usr/local/lib/android/sdk/ndk/$NDK_VERSION"; do
    [ -d "$d" ] && NDK="$d" && break
  done
fi
if [ -z "$NDK" ] || [ ! -d "$NDK" ]; then
  echo "error: Android NDK $NDK_VERSION not found." >&2
  echo "       Install it via the Android Studio SDK Manager, or set NDK_HOME." >&2
  exit 1
fi

found_version="$(sed -n 's/^Pkg.Revision *= *//p' "$NDK/source.properties" 2>/dev/null || true)"
if [ "$found_version" != "$NDK_VERSION" ]; then
  if [ "${ALLOW_ANY_NDK:-0}" = "1" ]; then
    echo "warning: building with NDK ${found_version:-unknown} instead of the pinned $NDK_VERSION" >&2
  else
    echo "error: $NDK is NDK ${found_version:-unknown}, the build is pinned to $NDK_VERSION." >&2
    echo "       Set ALLOW_ANY_NDK=1 to build with it anyway." >&2
    exit 1
  fi
fi

case "$(uname -s)" in
  Darwin) HOST="darwin-x86_64" ;;
  Linux)  HOST="linux-x86_64"  ;;
  *) echo "error: unsupported host platform" >&2; exit 1 ;;
esac
TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/$HOST/bin"

# ── Sources ──────────────────────────────────────────────────────────────────

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
prepare_libsmb2_sources "$BUILD_DIR"
libsmb2_sources
write_export_lists "$BUILD_DIR"

echo "=== libsmb2: building for Android ==="
echo "    NDK:     $NDK ($found_version)"
echo "    API:     $API"
echo "    Sources: ${#SOURCES[@]} files"
mkdir -p "$OUTPUT_DIR"

cc_for_abi() {
  case "$1" in
    arm64-v8a)   echo "aarch64-linux-android"    ;;
    armeabi-v7a) echo "armv7a-linux-androideabi" ;;
    x86_64)      echo "x86_64-linux-android"     ;;
    *)           echo "" ;;
  esac
}

build_abi() {
  local abi="$1" prefix
  prefix="$(cc_for_abi "$abi")"
  [ -n "$prefix" ] || { echo "error: unknown ABI: $abi" >&2; exit 1; }
  local cc="$TOOLCHAIN/${prefix}${API}-clang"
  [ -f "$cc" ] || { echo "error: compiler not found: $cc" >&2; exit 1; }

  local build="$BUILD_DIR/$abi"
  rm -rf "$build"
  echo ""
  echo "  Compiling $abi..."
  compile_objects "$build" "$cc" --

  echo "  Linking $abi..."
  # No SONAME: Flutter bundles the file under the name the package gives it.
  # -s drops the static symbol table (the Android Gradle plugin would strip
  # it anyway); the exported API lives in .dynsym, which stays.
  "$cc" -shared -s -o "$build/libsmb2.so" "$build"/*.o \
    -Wl,--version-script="$BUILD_DIR/exports.ver" \
    -Wl,--build-id=none \
    -Wl,--as-needed

  local output="$OUTPUT_DIR/libsmb2_android-${abi}.so"
  cp "$build/libsmb2.so" "$output"
  echo "  Output: $output ($(du -h "$output" | cut -f1))"
}

IFS=',' read -ra ABIS_LIST <<< "${ABIS:-arm64-v8a,armeabi-v7a,x86_64}"
for abi in "${ABIS_LIST[@]}"; do
  build_abi "$abi"
done

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_android-*.so"

if [ "${KEEP_BUILD:-0}" != "1" ]; then rm -rf "$BUILD_DIR"; fi
