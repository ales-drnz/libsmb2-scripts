#!/usr/bin/env bash
# =============================================================================
# build_macos.sh
#
# Compiles libsmb2 + smb2_wrapper.c into a dynamic libsmb2.framework wrapped
# in an xcframework for macOS (arm64 + x86_64 universal).
#
# Output:  release_builds/libsmb2_macos.xcframework.zip
# Source:  src/smb2_wrapper.c + pinned libsmb2 (fetched + patched at build time)
#
# Usage:
#   chmod +x scripts/build_macos.sh
#   ./scripts/build_macos.sh
#
# Options:
#   DEPLOYMENT_TARGET=10.14   (default: 10.14)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"

DEPLOYMENT_TARGET="${DEPLOYMENT_TARGET:-10.14}"

BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-macos}"

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

echo "=== libsmb2: building dynamic libsmb2.xcframework for macOS ==="
echo "    Sources: ${#SOURCES[@]} files"

# ── Build function ───────────────────────────────────────────────────────────

build_arch() {
  local arch="$1"
  local build="$BUILD_DIR/$arch"
  rm -rf "$build"
  mkdir -p "$build"

  echo "  Compiling for $arch..."
  for src in "${SOURCES[@]}"; do
    local name
    name="$(basename "${src%.c}").o"
    xcrun clang -c "$src" \
      -arch "$arch" \
      -mmacosx-version-min="$DEPLOYMENT_TARGET" \
      "${INCLUDES[@]}" \
      "${CFLAGS[@]}" \
      -o "$build/$name" &
  done
  wait

  echo "  Linking $arch..."
  xcrun clang \
    -arch "$arch" \
    -mmacosx-version-min="$DEPLOYMENT_TARGET" \
    -dynamiclib \
    -install_name "@rpath/libsmb2.framework/libsmb2" \
    -o "$build/libsmb2" \
    "$build"/*.o
}

# ── Build all archs + fat ────────────────────────────────────────────────────

build_arch arm64
build_arch x86_64

mkdir -p "$BUILD_DIR/fat"
echo "  Lipo arm64 + x86_64..."
xcrun lipo -create "$BUILD_DIR/arm64/libsmb2" "$BUILD_DIR/x86_64/libsmb2" \
  -output "$BUILD_DIR/fat/libsmb2"

# ── Assemble the .framework bundle (macOS layout: Versions/A) ────────────────

FW="$BUILD_DIR/libsmb2.framework"
rm -rf "$FW"
mkdir -p "$FW/Versions/A/Resources"
cp "$BUILD_DIR/fat/libsmb2" "$FW/Versions/A/libsmb2"

cat > "$FW/Versions/A/Resources/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleExecutable</key><string>libsmb2</string>
  <key>CFBundleIdentifier</key><string>com.ales-drnz.libsmb2</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>libsmb2</string>
  <key>CFBundlePackageType</key><string>FMWK</string>
  <key>CFBundleShortVersionString</key><string>6.1.0</string>
  <key>CFBundleVersion</key><string>6.1.0</string>
</dict>
</plist>
PLIST

# Symlinks: Versions/Current -> A, then top-level libsmb2/Resources -> Versions/Current/...
(cd "$FW/Versions" && ln -sfh A Current)
(cd "$FW" && ln -sfh Versions/Current/libsmb2 libsmb2 && ln -sfh Versions/Current/Resources Resources)

# ── Create xcframework ───────────────────────────────────────────────────────

echo ""
echo "  Creating xcframework..."
mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"

xcodebuild -create-xcframework \
  -framework "$FW" \
  -output "$OUTPUT_DIR/libsmb2.xcframework"

# ── Verify ───────────────────────────────────────────────────────────────────

echo ""
echo "Slice:"
xcrun lipo -info "$OUTPUT_DIR/libsmb2.xcframework"/*/libsmb2.framework/Versions/A/libsmb2 2>/dev/null || \
xcrun lipo -info "$OUTPUT_DIR/libsmb2.xcframework"/*/libsmb2.framework/libsmb2 2>/dev/null

# ── Zip ──────────────────────────────────────────────────────────────────────

echo ""
echo "  Zipping xcframework..."
rm -f "$OUTPUT_DIR/libsmb2_macos.xcframework.zip"
# -y preserves symlinks (Versions/Current → A, libsmb2 → Versions/Current/libsmb2)
# which are required by macOS framework loaders.
(cd "$OUTPUT_DIR" && zip -r -y -q libsmb2_macos.xcframework.zip libsmb2.xcframework)
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_macos.xcframework.zip ($(du -h "$OUTPUT_DIR/libsmb2_macos.xcframework.zip" | cut -f1))"

# ── Cleanup ──────────────────────────────────────────────────────────────────

rm -rf "$BUILD_DIR"
