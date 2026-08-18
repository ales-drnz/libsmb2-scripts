#!/usr/bin/env bash
# =============================================================================
# build_android.sh
#
# Cross-compiles libsmb2 + smb2_wrapper.c into shared libraries for Android.
#
# === OUTPUT FORMATS AND LOCATIONS ===
# Target Dir:  release/
# Output Files: libsmb2_android-arm64-v8a.so
#               libsmb2_android-armeabi-v7a.so
#               libsmb2_android-x86_64.so
#
# === SYSTEM & HARDWARE SPECS ===
# Target OS:   Android (API 24+)
# Target Arch: arm64-v8a, armeabi-v7a, x86_64
# Compiler:    Android NDK clang
#
# Usage (from project root):
#   chmod +x scripts/build_android.sh
#   NDK_HOME=/path/to/ndk ./scripts/build_android.sh
#
# Options (environment variables):
#   NDK_HOME=...       Path to the Android NDK root (also accepts ANDROID_NDK_HOME)
#   NDK_VERSION=...    Preferred NDK semantic version (default: 28.2.13676358 = r28c)
#   ANDROID_API=24     Minimum API level (default: 24)
#   ABIS=arm64-v8a     Comma-separated ABI list (default: arm64-v8a,armeabi-v7a,x86_64)
#   JOBS=N             Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1       Do not delete intermediate build directory
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"

API="${ANDROID_API:-24}"
# Guard: this library officially supports Android 7.0+ (API 24+). Building against
# a lower API would produce a .so that contradicts the Gradle minSdk and README.
if ! [[ "$API" =~ ^[0-9]+$ ]] || (( API < 24 )); then
  echo "ERROR: ANDROID_API must be >= 24 (got '$API'). Android 7.0+ is the supported floor." >&2
  exit 1
fi
JOBS="${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo 4)}"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-android}"

# Pinned NDK version. Kept in sync with Flutter's default (flutter.ndkVersion),
# so a single NDK install on the system covers the whole toolchain and
# prevents Gradle from auto-downloading a different version.
NDK_VERSION="${NDK_VERSION:-28.2.13676358}"

# ── Locate NDK ────────────────────────────────────────────────────────────────

NDK="${NDK_HOME:-${ANDROID_NDK_HOME:-${ANDROID_NDK:-}}}"

# Preferisce la versione pinnata; se non presente, fallback al primo NDK trovato.
if [ -z "$NDK" ]; then
  for d in \
    "$HOME/Library/Android/sdk/ndk/$NDK_VERSION" \
    "$HOME/Android/Sdk/ndk/$NDK_VERSION" \
    "/opt/android-ndk-$NDK_VERSION" \
    "/usr/local/lib/android/sdk/ndk/$NDK_VERSION"; do
    [ -d "$d" ] && NDK="$d" && break
  done
fi

if [ -z "$NDK" ]; then
  for d in \
    "$HOME/Library/Android/sdk/ndk/"* \
    "$HOME/Android/Sdk/ndk/"* \
    /opt/android-ndk* \
    /usr/local/lib/android/sdk/ndk/*; do
    [ -d "$d" ] && NDK="$d" && break
  done
  if [ -n "$NDK" ]; then
    echo "warning: pinned NDK $NDK_VERSION not found, falling back to $NDK" >&2
  fi
fi

if [ -z "$NDK" ] || [ ! -d "$NDK" ]; then
  echo "error: Android NDK not found." >&2
  echo "       Install NDK $NDK_VERSION via Android Studio SDK Manager," >&2
  echo "       or set NDK_HOME to the NDK root directory." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) HOST="darwin-x86_64" ;;
  Linux)  HOST="linux-x86_64"  ;;
  *) echo "error: unsupported host platform" >&2; exit 1 ;;
esac

TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/$HOST/bin"

# ── Fetch + patch sources ────────────────────────────────────────────────────

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
prepare_libsmb2_sources "$BUILD_DIR"

SOURCES=("$LIBSMB2_SCRIPTS_ROOT/src/smb2_wrapper.c")
for f in "$SMB2_SRC"/lib/*.c; do
  case "$(basename "$f")" in
    krb5-wrapper.c) continue ;;
    *) SOURCES+=("$f") ;;
  esac
done

INCLUDES=(
  "-I$SMB2_SRC/include"
  "-I$SMB2_SRC/include/smb2"
  "-I$SMB2_SRC/lib"
)

CFLAGS=(
  -O2
  -DHAVE_CONFIG_H=1
  -fPIC
  -w
)

echo "=== libsmb2: building for Android ==="
echo "    NDK:     $NDK"
echo "    API:     $API"
echo "    Sources: ${#SOURCES[@]} files"

mkdir -p "$OUTPUT_DIR"

# ── Build function ────────────────────────────────────────────────────────────

build_abi() {
  local abi="$1"
  local cc_prefix="$2"
  local build="$BUILD_DIR/$abi"

  echo ""
  echo "  Building $abi..."
  rm -rf "$build"
  mkdir -p "$build"

  local CC="$TOOLCHAIN/${cc_prefix}${API}-clang"
  if [ ! -f "$CC" ]; then
    echo "error: compiler not found: $CC" >&2
    exit 1
  fi

  local pids=()
  for src in "${SOURCES[@]}"; do
    local name
    name="$(basename "${src%.c}").o"
    "$CC" -c "$src" \
      "${INCLUDES[@]}" \
      "${CFLAGS[@]}" \
      -o "$build/$name" &
    pids+=($!)
  done
  for pid in "${pids[@]}"; do wait "$pid"; done

  echo "  Linking $abi..."
  "$CC" \
    -shared \
    -o "$build/libsmb2.so" \
    "$build"/*.o \
    -llog

  local output="$OUTPUT_DIR/libsmb2_android-${abi}.so"
  cp "$build/libsmb2.so" "$output"
  echo "  Output: $output ($(du -h "$output" | cut -f1))"
}

# ── Build ─────────────────────────────────────────────────────────────────────

IFS=',' read -ra ABIS_LIST <<< "${ABIS:-arm64-v8a,armeabi-v7a,x86_64}"

cc_for_abi() {
  case "$1" in
    arm64-v8a)   echo "aarch64-linux-android"    ;;
    armeabi-v7a) echo "armv7a-linux-androideabi" ;;
    x86_64)      echo "x86_64-linux-android"     ;;
    *)           echo "" ;;
  esac
}

for abi in "${ABIS_LIST[@]}"; do
  cc_prefix="$(cc_for_abi "$abi")"
  if [ -z "$cc_prefix" ]; then
    echo "error: unknown ABI: $abi" >&2; exit 1
  fi
  build_abi "$abi" "$cc_prefix"
done

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_android-*.so"

[ "${KEEP_BUILD:-0}" != "1" ] && rm -rf "$BUILD_DIR"
