#!/usr/bin/env bash
# =============================================================================
# build_ios.sh
#
# Compiles libsmb2 + smb2_wrapper.c into a dynamic libsmb2.framework wrapped
# in an xcframework for iOS (device + simulator).
#
# Output:  release_builds/libsmb2_ios.xcframework.zip
#
# Source:  src/smb2_wrapper.c + pinned libsmb2 (fetched + patched at build time)
#
# Usage:
#   chmod +x scripts/build_ios.sh
#   ./scripts/build_ios.sh
#
# Options:
#   DEPLOYMENT_TARGET=12.0   (default: 12.0)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"
OUTPUT_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"

DEPLOYMENT_TARGET="${DEPLOYMENT_TARGET:-12.0}"

BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-ios}"

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

CFLAGS_COMMON=(
  -O2
  -DHAVE_CONFIG_H=1
  -fPIC
  -w
)

echo "=== libsmb2: building dynamic libsmb2.xcframework for iOS ==="
echo "    Sources: ${#SOURCES[@]} files"

# ── Build function ───────────────────────────────────────────────────────────
#
# Compiles every source into an object, then links them into a single dynamic
# library with install_name set to @rpath/libsmb2.framework/libsmb2, and
# wraps it in a proper .framework bundle ready for xcodebuild -create-xcframework.

build_framework() {
  local label="$1"      # "device" | "simulator"
  local sdk="$2"        # "iphoneos" | "iphonesimulator"
  local suffix="$3"     # target triple suffix: "" or "-simulator"
  shift 3
  local archs=("$@")

  local sdk_path
  sdk_path="$(xcrun --sdk "$sdk" --show-sdk-path)"
  local build="$BUILD_DIR/$label"
  local arch_dylibs=()

  for arch in "${archs[@]}"; do
    local arch_dir="$build/$arch"
    rm -rf "$arch_dir"
    mkdir -p "$arch_dir"
    local target="${arch}-apple-ios${DEPLOYMENT_TARGET}${suffix}"

    echo "  Compiling $label/$arch (target: $target)..."
    for src in "${SOURCES[@]}"; do
      local name
      name="$(basename "${src%.c}").o"
      xcrun clang -c "$src" \
        -target "$target" \
        -isysroot "$sdk_path" \
        "${INCLUDES[@]}" \
        "${CFLAGS_COMMON[@]}" \
        -o "$arch_dir/$name" &
    done
    wait

    echo "  Linking $label/$arch..."
    xcrun clang \
      -target "$target" \
      -isysroot "$sdk_path" \
      -dynamiclib \
      -install_name "@rpath/libsmb2.framework/libsmb2" \
      -o "$arch_dir/libsmb2" \
      "$arch_dir"/*.o

    arch_dylibs+=("$arch_dir/libsmb2")
  done

  # Lipo if multiple archs (simulator: arm64 + x86_64)
  mkdir -p "$build/fat"
  if [ ${#arch_dylibs[@]} -gt 1 ]; then
    echo "  Lipo $label (${archs[*]})..."
    xcrun lipo -create "${arch_dylibs[@]}" -output "$build/fat/libsmb2"
  else
    cp "${arch_dylibs[0]}" "$build/fat/libsmb2"
  fi

  # Assemble the .framework bundle.
  local fw="$build/libsmb2.framework"
  rm -rf "$fw"
  mkdir -p "$fw"
  cp "$build/fat/libsmb2" "$fw/libsmb2"

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
  <key>CFBundleShortVersionString</key><string>6.1.0</string>
  <key>CFBundleVersion</key><string>6.1.0</string>
  <key>MinimumOSVersion</key><string>${DEPLOYMENT_TARGET}</string>
  <key>CFBundleSupportedPlatforms</key><array>
    <string>$([ "$sdk" = "iphoneos" ] && echo iPhoneOS || echo iPhoneSimulator)</string>
  </array>
</dict>
</plist>
PLIST
}

# ── Build both slices ────────────────────────────────────────────────────────

build_framework "device"    "iphoneos"        ""           arm64
build_framework "simulator" "iphonesimulator" "-simulator" arm64 x86_64

# ── Create xcframework ───────────────────────────────────────────────────────

echo ""
echo "  Creating xcframework..."
mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"

xcodebuild -create-xcframework \
  -framework "$BUILD_DIR/device/libsmb2.framework" \
  -framework "$BUILD_DIR/simulator/libsmb2.framework" \
  -output "$OUTPUT_DIR/libsmb2.xcframework"

# ── Verify ───────────────────────────────────────────────────────────────────

echo ""
echo "Slices:"
for fw in "$OUTPUT_DIR"/libsmb2.xcframework/*/libsmb2.framework/libsmb2; do
  echo "  $(xcrun lipo -info "$fw" 2>/dev/null)"
done

# ── Zip ──────────────────────────────────────────────────────────────────────

echo ""
echo "  Zipping xcframework..."
rm -f "$OUTPUT_DIR/libsmb2_ios.xcframework.zip"
(cd "$OUTPUT_DIR" && zip -r -q libsmb2_ios.xcframework.zip libsmb2.xcframework)
rm -rf "$OUTPUT_DIR/libsmb2.xcframework"

echo ""
echo "=== Done ==="
echo "Output: $OUTPUT_DIR/libsmb2_ios.xcframework.zip ($(du -h "$OUTPUT_DIR/libsmb2_ios.xcframework.zip" | cut -f1))"

# ── Cleanup ──────────────────────────────────────────────────────────────────

rm -rf "$BUILD_DIR"
