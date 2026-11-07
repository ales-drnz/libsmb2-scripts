#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# build_libsmb2_macos.sh
#
# Compiles libsmb2 into a dynamic libsmb2.framework for macOS (arm64 +
# x86_64 universal), wrapped in an xcframework, with the pinned OpenSSL's
# libcrypto built for each arch (darwin64-arm64, darwin64-x86_64) and linked
# in statically.
#
# Output: release_builds/libsmb2_macos.xcframework.zip, with licenses/libsmb2/
#         and licenses/openssl/ beside the xcframework
#
# Target: macOS 10.15+ (Flutter's floor). Needs macOS with Xcode, and perl
# and make (both come with the command line tools) for OpenSSL's Configure.
#
# The dylibs link with -Wl,-x, which drops the local symbols as strip -x
# does (the exported API stays); the linker signs after it, so the
# ad-hoc signature of the arm64 slice stays valid.
#
# Usage (from the repo root): scripts/build_libsmb2_macos.sh
#
# Options (environment variables):
#   DEPLOYMENT_TARGET=10.15  Minimum macOS version
#   JOBS=N                   Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1             Do not delete the intermediate build directory
#   FORCE_DOWNLOAD=1         Redownload the libsmb2 and OpenSSL tarballs even if cached
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-macos}"
DEPLOYMENT_TARGET="${DEPLOYMENT_TARGET:-10.15}"

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
prepare_libsmb2_sources "$BUILD_DIR"
prepare_openssl_sources "$BUILD_DIR"
libsmb2_sources
write_export_lists "$BUILD_DIR"

echo "=== libsmb2: building libsmb2.xcframework for macOS ==="
echo "    Sources: ${#SOURCES[@]} files"

build_arch() {
  local arch="$1" dir="$BUILD_DIR/$1"
  rm -rf "$dir"
  # libcrypto with the same compiler and minimum macOS; the target adds
  # -arch.
  CC="xcrun clang" build_libcrypto "$BUILD_DIR/openssl-$arch" "darwin64-$arch" \
    -mmacosx-version-min="$DEPLOYMENT_TARGET"

  echo "  Compiling $arch..."
  compile_objects "$dir" xcrun clang -- -arch "$arch" -mmacosx-version-min="$DEPLOYMENT_TARGET" \
    "${OPENSSL_INCLUDES[@]}"

  echo "  Linking $arch..."
  # libcrypto.a comes after the objects, so only what they use is linked;
  # the exported symbols list keeps its symbols private.
  xcrun clang -arch "$arch" -mmacosx-version-min="$DEPLOYMENT_TARGET" \
    -dynamiclib \
    -install_name "@rpath/libsmb2.framework/libsmb2" \
    -compatibility_version 1 -current_version 1 \
    -Wl,-exported_symbols_list,"$BUILD_DIR/exports.txt" \
    -Wl,-x \
    -Wl,-dead_strip \
    -o "$dir/libsmb2" "$dir"/*.o "$LIBCRYPTO"
}

build_arch arm64
build_arch x86_64

# The framework uses the macOS layout: Versions/A plus the Current and
# top-level symlinks, which the zip below keeps (-y).
FW="$BUILD_DIR/libsmb2.framework"
rm -rf "$FW"
mkdir -p "$FW/Versions/A/Resources"
echo "  Lipo arm64 + x86_64..."
xcrun lipo -create "$BUILD_DIR/arm64/libsmb2" "$BUILD_DIR/x86_64/libsmb2" \
  -output "$FW/Versions/A/libsmb2"

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
  <key>CFBundleShortVersionString</key><string>${LIBSMB2_BUNDLE_VERSION}</string>
  <key>CFBundleVersion</key><string>${LIBSMB2_BUNDLE_VERSION}</string>
  <key>LSMinimumSystemVersion</key><string>${DEPLOYMENT_TARGET}</string>
</dict>
</plist>
PLIST

(cd "$FW/Versions" && ln -sfh A Current)
(cd "$FW" && ln -sfh Versions/Current/libsmb2 libsmb2 && ln -sfh Versions/Current/Resources Resources)

echo ""
echo "  Creating xcframework..."
mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"
xcodebuild -create-xcframework -framework "$FW" -output "$OUTPUT_DIR/libsmb2.xcframework"

echo ""
echo "Slice:"
xcrun lipo -info "$OUTPUT_DIR"/libsmb2.xcframework/*/libsmb2.framework/Versions/A/libsmb2

echo ""
echo "  Zipping xcframework..."
zip_xcframework "$OUTPUT_DIR" libsmb2_macos.xcframework.zip

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_macos.xcframework.zip ($(du -h "$OUTPUT_DIR/libsmb2_macos.xcframework.zip" | cut -f1))"

if [ "${KEEP_BUILD:-0}" != "1" ]; then rm -rf "$BUILD_DIR"; fi
