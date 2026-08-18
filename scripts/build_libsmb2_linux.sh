#!/usr/bin/env bash
# =============================================================================
# build_libsmb2_linux.sh
#
# Fetches the pinned libsmb2 source, applies the patch set, and compiles
# libsmb2 + smb2_wrapper.c into shared libraries for Linux.
#
# === OUTPUT FORMATS AND LOCATIONS ===
# Target Dir:  release_builds/
# Output Files: libsmb2_linux-x86_64.so
#               libsmb2_linux-aarch64.so
#
# === SYSTEM & HARDWARE SPECS ===
# Target OS:   Linux
# Target Arch: x86_64, aarch64
# Compiler:    gcc (native x86_64) + aarch64-linux-gnu-gcc (cross)
#
# Usage (from project root):
#   chmod +x scripts/build_libsmb2_linux.sh
#   ./scripts/build_libsmb2_linux.sh
#
# Requirements (Ubuntu/Debian):
#   sudo apt install gcc gcc-aarch64-linux-gnu python3 curl
#
# Options (environment variables):
#   ARCHS=...         Comma-separated arch list (default: x86_64,aarch64)
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
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-linux}"

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

cc_for_arch() {
  case "$1" in
    x86_64)   echo "gcc" ;;
    aarch64)  echo "aarch64-linux-gnu-gcc" ;;
    *)        echo "" ;;
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
      x86_64)  echo "       Install with: sudo apt install gcc" >&2 ;;
      aarch64) echo "       Install with: sudo apt install gcc-aarch64-linux-gnu" >&2 ;;
    esac
    exit 1
  fi

  local build="$BUILD_DIR/$arch"
  rm -rf "$build"
  mkdir -p "$build"

  echo ""
  echo "  Building $arch with $cc..."

  local pids=()
  for src in "${SOURCES[@]}"; do
    local name
    name="$(basename "${src%.c}").o"
    "$cc" -c "$src" \
      "${INCLUDES[@]}" \
      "${CFLAGS[@]}" \
      -o "$build/$name" &
    pids+=($!)
  done
  for pid in "${pids[@]}"; do wait "$pid"; done

  echo "  Linking $arch..."
  "$cc" \
    -shared \
    -o "$build/libsmb2.so" \
    "$build"/*.o

  local output="$OUTPUT_DIR/libsmb2_linux-${arch}.so"
  cp "$build/libsmb2.so" "$output"
  echo "  Output: $output ($(du -h "$output" | cut -f1))"
}

# ── Build ─────────────────────────────────────────────────────────────────────

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

[ "${KEEP_BUILD:-0}" != "1" ] && rm -rf "$BUILD_DIR"
