#!/usr/bin/env bash
# =============================================================================
# build_windows.sh
#
# Cross-compiles libsmb2 + smb2_wrapper.c into DLLs for Windows.
# Must be run from Linux using MinGW-w64.
#
# === OUTPUT FORMATS AND LOCATIONS ===
# Target Dir:  release/
# Output Files: libsmb2_windows-x86_64.dll
#               libsmb2_windows-arm64.dll
#
# === SYSTEM & HARDWARE SPECS ===
# Target OS:   Windows (x86_64, arm64)
# Host OS:     Linux
# Compiler:    MinGW-w64 (x86_64-w64-mingw32-gcc, aarch64-w64-mingw32-clang)
#
# Usage (from project root):
#   chmod +x scripts/build_libsmb2_windows.sh
#   ./scripts/build_libsmb2_windows.sh
#
# Requirements (Ubuntu/Debian):
#   sudo apt install gcc-mingw-w64-x86-64 python3 curl
#   # arm64 cross-compilation uses LLVM-MinGW from
#   # https://github.com/mstorsjo/llvm-mingw — install under /opt/llvm-mingw.
#
# Options (environment variables):
#   ARCHS=...         Comma-separated arch list (default: x86_64,arm64)
#   JOBS=N            Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1      Do not delete intermediate build directory
#   FORCE_DOWNLOAD=1  Redownload the libsmb2 tarball even if cached
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"

JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-windows}"

# ── Fetch + patch sources ────────────────────────────────────────────────────

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
PATCH_PLATFORM=windows prepare_libsmb2_sources "$BUILD_DIR"

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
  -D_WINDOWS
  -D_CRT_SECURE_NO_WARNINGS
  -fPIC
  -w
)

cc_for_arch() {
  case "$1" in
    x86_64) echo "x86_64-w64-mingw32-gcc" ;;
    arm64)  echo "aarch64-w64-mingw32-clang" ;;
    *)      echo "" ;;
  esac
}

build_arch() {
  local arch="$1"
  local cc
  cc="$(cc_for_arch "$arch")"
  if [ -z "$cc" ]; then
    echo "error: unknown arch: $arch" >&2; exit 1
  fi
  if ! command -v "$cc" &>/dev/null; then
    echo "error: $cc not found." >&2
    case "$arch" in
      x86_64) echo "       Install with: sudo apt install gcc-mingw-w64-x86-64" >&2 ;;
      arm64)  echo "       Install LLVM-MinGW (https://github.com/mstorsjo/llvm-mingw)" >&2
              echo "       and ensure aarch64-w64-mingw32-clang is on PATH." >&2 ;;
    esac
    exit 1
  fi

  local build="$BUILD_DIR/$arch"
  rm -rf "$build"
  mkdir -p "$build"

  echo ""
  echo "  Building $arch with $cc..."

  local running=0
  for src in "${SOURCES[@]}"; do
    local name
    name="$(basename "${src%.c}").o"
    "$cc" -c "$src" \
      "${INCLUDES[@]}" \
      "${CFLAGS[@]}" \
      -o "$build/$name" &
    running=$((running + 1))
    if [ "$running" -ge "$JOBS" ]; then
      wait -n
      running=$((running - 1))
    fi
  done
  wait

  echo "  Linking $arch..."
  "$cc" \
    -shared \
    -static \
    -static-libgcc \
    -o "$build/libsmb2.dll" \
    "$build"/*.o \
    -Wl,-Bstatic -lpthread \
    -lws2_32 \
    -Wl,--export-all-symbols

  local output="$OUTPUT_DIR/libsmb2_windows-${arch}.dll"
  cp "$build/libsmb2.dll" "$output"
  echo "  Output: $output ($(du -h "$output" | cut -f1))"
}

# ── Build ─────────────────────────────────────────────────────────────────────

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

[ "${KEEP_BUILD:-0}" != "1" ] && rm -rf "$BUILD_DIR"
