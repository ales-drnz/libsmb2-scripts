#!/usr/bin/env bash
# =============================================================================
# bump_version.sh
#
# Updates the library version and/or binary release version across every
# platform-specific file in one shot:
#   pubspec.yaml             — library version
#   ios/dart_smb2.podspec    — library version + release tag
#   macos/dart_smb2.podspec  — library version + release tag
#   ios/dart_smb2/Package.swift   — release tag in binaryTarget URL
#   macos/dart_smb2/Package.swift — release tag in binaryTarget URL
#   android/build.gradle.kts — library version + release tag
#   linux/CMakeLists.txt     — release tag
#   windows/CMakeLists.txt   — release tag
#   README.md                — install snippet (`dart_smb2: ^X.Y.Z`)
#
# Usage (from libsmb2-scripts/):
#   ./scripts/bump_version.sh
#   ./build bump
#
# Edit these two variables, then run the script:
# =============================================================================

LIB_VERSION="0.1.2"           # Library version (pubspec, podspecs, gradle)
RELEASE_VERSION="libsmb2-r7"  # Binary release tag (GitHub release download URL)

# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
ROOT="$(resolve_repo_root)" || exit 1

# sed in-place that works on both macOS and Linux
sedi() {
  if [[ "$OSTYPE" == darwin* ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

echo "=== dart_smb2: bumping versions ==="
echo "  Library version:  $LIB_VERSION"
echo "  Release version:  $RELEASE_VERSION"
echo ""

# ── Library version ──────────────────────────────────────────────────────────

# pubspec.yaml
sedi "s|^version: .*|version: $LIB_VERSION|" "$ROOT/pubspec.yaml"
echo "  pubspec.yaml                -> $LIB_VERSION"

# macOS podspec
sedi "s|s\.version *= *'[^']*'|s.version          = '$LIB_VERSION'|" "$ROOT/macos/dart_smb2.podspec"
echo "  macos/dart_smb2.podspec     -> $LIB_VERSION"

# iOS podspec
sedi "s|s\.version *= *'[^']*'|s.version          = '$LIB_VERSION'|" "$ROOT/ios/dart_smb2.podspec"
echo "  ios/dart_smb2.podspec       -> $LIB_VERSION"

# Android build.gradle.kts (top-level `version = "..."`)
sedi "s|^version = \"[^\"]*\"|version = \"$LIB_VERSION\"|" "$ROOT/android/build.gradle.kts"
echo "  android/build.gradle.kts    -> $LIB_VERSION"

# ── Release version (binary download tag) ────────────────────────────────────

# macOS podspec
sedi "s|RELEASE=\"[^\"]*\"|RELEASE=\"$RELEASE_VERSION\"|" "$ROOT/macos/dart_smb2.podspec"
echo "  macos podspec release       -> $RELEASE_VERSION"

# iOS podspec
sedi "s|RELEASE=\"[^\"]*\"|RELEASE=\"$RELEASE_VERSION\"|" "$ROOT/ios/dart_smb2.podspec"
echo "  ios podspec release         -> $RELEASE_VERSION"

# Android build.gradle.kts (`val SMB2_RELEASE_VERSION = "..."`)
sedi "s|val SMB2_RELEASE_VERSION = \"[^\"]*\"|val SMB2_RELEASE_VERSION = \"$RELEASE_VERSION\"|" "$ROOT/android/build.gradle.kts"
echo "  android gradle release      -> $RELEASE_VERSION"

# Linux CMakeLists.txt
sedi "s|set(SMB2_RELEASE_VERSION \"[^\"]*\")|set(SMB2_RELEASE_VERSION \"$RELEASE_VERSION\")|" "$ROOT/linux/CMakeLists.txt"
echo "  linux CMakeLists release    -> $RELEASE_VERSION"

# Windows CMakeLists.txt
sedi "s|set(SMB2_RELEASE_VERSION \"[^\"]*\")|set(SMB2_RELEASE_VERSION \"$RELEASE_VERSION\")|" "$ROOT/windows/CMakeLists.txt"
echo "  windows CMakeLists release  -> $RELEASE_VERSION"

# SwiftPM Package.swift binaryTarget URLs (iOS + macOS) — the release tag
# is embedded in the GitHub Releases download URL.
sedi -E "s|releases/download/[^/]+/|releases/download/$RELEASE_VERSION/|" "$ROOT/ios/dart_smb2/Package.swift"
echo "  ios Package.swift release   -> $RELEASE_VERSION"
sedi -E "s|releases/download/[^/]+/|releases/download/$RELEASE_VERSION/|" "$ROOT/macos/dart_smb2/Package.swift"
echo "  macos Package.swift release -> $RELEASE_VERSION"

# README install snippet (`dart_smb2: ^X.Y.Z`)
sedi "s|dart_smb2: \^[0-9][0-9.+-]*|dart_smb2: ^$LIB_VERSION|" "$ROOT/README.md"
echo "  README.md install snippet   -> $LIB_VERSION"

echo ""
echo "Done. Run 'make checksums' after building to update SHA-256 hashes."
