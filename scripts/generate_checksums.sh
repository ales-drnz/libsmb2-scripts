#!/usr/bin/env bash
# =============================================================================
# generate_checksums.sh
#
# Computes SHA-256 checksums for all release binaries (macOS xcframework, iOS
# xcframework, Android arm64-v8a + armeabi-v7a + x86_64, Linux x86_64 +
# aarch64, Windows x86_64 + arm64), updates them in-place in the platform
# build files, and copies each library to its per-arch destination directory.
#
# Layout installed into the consumer repo:
#   linux/libs/<arch>/libsmb2.so
#   windows/libs/<arch>/libsmb2.dll
#   android/src/main/jniLibs/<abi>/libsmb2.so
#   macos/dart_smb2/Frameworks/libsmb2.xcframework   (extracted from .zip)
#   ios/dart_smb2/Frameworks/libsmb2.xcframework     (extracted from .zip)
# Plus the SHA-256 written into each platform's build file (CMakeLists.txt /
# build.gradle.kts / dart_smb2.podspec / Package.swift). The build scripts
# emit ONLY to release_builds/ — this script is the single point that
# installs artifacts into the consumer repo.
#
# Usage (from libsmb2-scripts/):
#   ./scripts/generate_checksums.sh
#   ./build checksums
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
ROOT="$(resolve_repo_root)" || exit 1
RELEASE_DIR="$LIBSMB2_SCRIPTS_ROOT/release_builds"

sha256() {
  if command -v sha256sum &>/dev/null; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# sed in-place that works on both macOS and Linux
sedi() {
  if [[ "$OSTYPE" == darwin* ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

# Update a per-arch SHA-256 variable in a CMakeLists.txt:
#   set(EXPECTED_SHA256_X86_64  "...")
update_cmake_arch_sha() {
  local cmake_file="$1" var_name="$2" new_hash="$3"
  sedi -E "s|set\\(${var_name}[[:space:]]+\"[a-f0-9]{64}\"\\)|set(${var_name}  \"$new_hash\")|" "$cmake_file"
}

# Update an Android per-ABI SHA-256 inside build.gradle.kts. The map entries
# look like:
#   "armeabi-v7a" to mapOf(
#       "file"   to "libsmb2_android-armeabi-v7a.so",
#       "sha256" to "<hash>"
#   ),
update_android_sha() {
  local gradle_file="$1" abi_filename="$2" new_hash="$3"
  perl -i -0777 -pe \
    "s|(\"file\" to \"\Q$abi_filename\E\",\s*\"sha256\" to \")[a-f0-9]{64}|\${1}$new_hash|" \
    "$gradle_file"
}

echo "=== dart_smb2: updating checksums + copying libraries ==="
echo ""

errors=0

# ── macOS xcframework (universal: arm64 + x86_64) ───────────────────────────

FILE="$RELEASE_DIR/libsmb2_macos.xcframework.zip"
if [ -f "$FILE" ]; then
  HASH=$(sha256 "$FILE")
  sedi "s|EXPECTED_SHA=\"[a-f0-9]\{64\}\"|EXPECTED_SHA=\"$HASH\"|" "$ROOT/macos/dart_smb2.podspec"
  sedi -E "s|(checksum:[[:space:]]*\")[a-f0-9]{64}|\\1$HASH|" "$ROOT/macos/dart_smb2/Package.swift"
  # Extract the xcframework into the consumer's Frameworks/ slot — inside the
  # SwiftPM package dir, so Package.swift's local layout and the podspec's
  # vendored_frameworks point at the same path (gitignored).
  DEST="$ROOT/macos/dart_smb2/Frameworks"
  mkdir -p "$DEST"
  rm -rf "$DEST/libsmb2.xcframework"
  unzip -q -o "$FILE" -d "$DEST"
  echo "  macos xcframework: $HASH"
  echo "    -> $DEST/libsmb2.xcframework"
else
  echo "  macos xcframework: NOT FOUND"
  errors=$((errors + 1))
fi

# ── iOS xcframework (device arm64 + simulator arm64/x86_64) ─────────────────

FILE="$RELEASE_DIR/libsmb2_ios.xcframework.zip"
if [ -f "$FILE" ]; then
  HASH=$(sha256 "$FILE")
  sedi "s|EXPECTED_SHA=\"[a-f0-9]\{64\}\"|EXPECTED_SHA=\"$HASH\"|" "$ROOT/ios/dart_smb2.podspec"
  sedi -E "s|(checksum:[[:space:]]*\")[a-f0-9]{64}|\\1$HASH|" "$ROOT/ios/dart_smb2/Package.swift"
  DEST="$ROOT/ios/dart_smb2/Frameworks"
  mkdir -p "$DEST"
  rm -rf "$DEST/libsmb2.xcframework"
  unzip -q -o "$FILE" -d "$DEST"
  echo "  ios xcframework:   $HASH"
  echo "    -> $DEST/libsmb2.xcframework"
else
  echo "  ios xcframework: NOT FOUND"
  errors=$((errors + 1))
fi

# ── Android (arm64-v8a, armeabi-v7a, x86_64) ────────────────────────────────

GRADLE="$ROOT/android/build.gradle.kts"

for abi in arm64-v8a armeabi-v7a x86_64; do
  FILE="$RELEASE_DIR/libsmb2_android-${abi}.so"
  if [ -f "$FILE" ]; then
    HASH=$(sha256 "$FILE")
    DEST="$ROOT/android/src/main/jniLibs/$abi"
    mkdir -p "$DEST"
    cp "$FILE" "$DEST/libsmb2.so"
    update_android_sha "$GRADLE" "libsmb2_android-${abi}.so" "$HASH"
    printf "  android %-13s %s\n" "$abi:" "$HASH"
    echo "    -> android/src/main/jniLibs/$abi/libsmb2.so"
  else
    echo "  android $abi: NOT FOUND"
    errors=$((errors + 1))
  fi
done

# ── Linux (x86_64, aarch64) — arch-scoped subdirs ───────────────────────────

LINUX_CMAKE="$ROOT/linux/CMakeLists.txt"

for arch in x86_64 aarch64; do
  FILE="$RELEASE_DIR/libsmb2_linux-${arch}.so"
  if [ -f "$FILE" ]; then
    HASH=$(sha256 "$FILE")
    DEST="$ROOT/linux/libs/$arch"
    mkdir -p "$DEST"
    cp "$FILE" "$DEST/libsmb2.so"
    arch_upper=$(echo "$arch" | tr '[:lower:]' '[:upper:]')
    update_cmake_arch_sha "$LINUX_CMAKE" "EXPECTED_SHA256_${arch_upper}" "$HASH"
    printf "  linux %-9s %s\n" "$arch:" "$HASH"
    echo "    -> linux/libs/$arch/libsmb2.so"
  else
    echo "  linux $arch: NOT FOUND"
    errors=$((errors + 1))
  fi
done

# ── Windows (x86_64, arm64) — arch-scoped subdirs ───────────────────────────

WINDOWS_CMAKE="$ROOT/windows/CMakeLists.txt"

for arch in x86_64 arm64; do
  FILE="$RELEASE_DIR/libsmb2_windows-${arch}.dll"
  if [ -f "$FILE" ]; then
    HASH=$(sha256 "$FILE")
    DEST="$ROOT/windows/libs/$arch"
    mkdir -p "$DEST"
    cp "$FILE" "$DEST/libsmb2.dll"
    arch_upper=$(echo "$arch" | tr '[:lower:]' '[:upper:]')
    update_cmake_arch_sha "$WINDOWS_CMAKE" "EXPECTED_SHA256_${arch_upper}" "$HASH"
    printf "  windows %-7s %s\n" "$arch:" "$HASH"
    echo "    -> windows/libs/$arch/libsmb2.dll"
  else
    echo "  windows $arch: NOT FOUND"
    errors=$((errors + 1))
  fi
done

# ── Summary ─────────────────────────────────────────────────────────────────

echo ""
if [ $errors -eq 0 ]; then
  echo "All checksums updated and libraries copied."
else
  echo "WARNING: $errors binary(s) not found. Run the build scripts first."
  exit 1
fi
