#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# build_libsmb2_ios.sh
#
# Compiles libsmb2 into a dynamic libsmb2.framework for iOS devices (arm64)
# and the simulator (arm64 + x86_64), wrapped in one xcframework.
#
# Output: release_builds/libsmb2_ios.xcframework.zip, with licenses/libsmb2/
#         beside the xcframework
#
# Target: iOS 13.0+ (Flutter's floor). Needs macOS with Xcode.
#
# Usage (from the repo root): scripts/build_libsmb2_ios.sh
#
# Options (environment variables):
#   DEPLOYMENT_TARGET=13.0  Minimum iOS version
#   JOBS=N                  Parallel compile jobs (default: all cores)
#   KEEP_BUILD=1            Do not delete the intermediate build directory
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-ios}"
DEPLOYMENT_TARGET="${DEPLOYMENT_TARGET:-13.0}"

echo "=== libsmb2: preparing sources ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
prepare_libsmb2_sources "$BUILD_DIR"
libsmb2_sources
write_export_lists "$BUILD_DIR"

echo "=== libsmb2: building libsmb2.xcframework for iOS ==="
echo "    Sources: ${#SOURCES[@]} files"

# build_framework <label> <sdk> <triple suffix> <arch...>
# Compiles and links one dylib per arch, lipos them, and wraps the result in
# a flat iOS .framework bundle at $BUILD_DIR/<label>/libsmb2.framework.
build_framework() {
  local label="$1" sdk="$2" suffix="$3"
  shift 3
  local sdk_path build arch
  sdk_path="$(xcrun --sdk "$sdk" --show-sdk-path)"
  build="$BUILD_DIR/$label"
  local dylibs=()

  for arch in "$@"; do
    local dir="$build/$arch"
    local target="${arch}-apple-ios${DEPLOYMENT_TARGET}${suffix}"
    rm -rf "$dir"
    echo "  Compiling $label/$arch ($target)..."
    compile_objects "$dir" xcrun clang -- -target "$target" -isysroot "$sdk_path"

    echo "  Linking $label/$arch..."
    xcrun clang -target "$target" -isysroot "$sdk_path" \
      -dynamiclib \
      -install_name "@rpath/libsmb2.framework/libsmb2" \
      -compatibility_version 1 -current_version 1 \
      -Wl,-exported_symbols_list,"$BUILD_DIR/exports.txt" \
      -o "$dir/libsmb2" "$dir"/*.o
    dylibs+=("$dir/libsmb2")
  done

  local fw="$build/libsmb2.framework"
  rm -rf "$fw"
  mkdir -p "$fw"
  if [ "${#dylibs[@]}" -gt 1 ]; then
    xcrun lipo -create "${dylibs[@]}" -output "$fw/libsmb2"
  else
    cp "${dylibs[0]}" "$fw/libsmb2"
  fi

  local platform="iPhoneOS"
  [ "$sdk" = "iphonesimulator" ] && platform="iPhoneSimulator"
  cat > "$fw/Info.plist" <<PLIST
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
  <key>MinimumOSVersion</key><string>${DEPLOYMENT_TARGET}</string>
  <key>CFBundleSupportedPlatforms</key><array><string>${platform}</string></array>
</dict>
</plist>
PLIST
}

build_framework device    iphoneos        ""           arm64
build_framework simulator iphonesimulator "-simulator" arm64 x86_64

echo ""
echo "  Creating xcframework..."
mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"
xcodebuild -create-xcframework \
  -framework "$BUILD_DIR/device/libsmb2.framework" \
  -framework "$BUILD_DIR/simulator/libsmb2.framework" \
  -output "$OUTPUT_DIR/libsmb2.xcframework"

echo ""
echo "Slices:"
for bin in "$OUTPUT_DIR"/libsmb2.xcframework/*/libsmb2.framework/libsmb2; do
  echo "  $(xcrun lipo -info "$bin")"
done

echo ""
echo "  Zipping xcframework..."
rm -f "$OUTPUT_DIR/libsmb2_ios.xcframework.zip"
(cd "$OUTPUT_DIR" && zip -r -X -q libsmb2_ios.xcframework.zip libsmb2.xcframework)
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"
add_licenses_to_zip "$OUTPUT_DIR/libsmb2_ios.xcframework.zip"

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_ios.xcframework.zip ($(du -h "$OUTPUT_DIR/libsmb2_ios.xcframework.zip" | cut -f1))"

if [ "${KEEP_BUILD:-0}" != "1" ]; then rm -rf "$BUILD_DIR"; fi
