# Shared helpers for the build_libsmb2_<platform>.sh scripts.
# Sourced by every script. Do not run directly.

# ── Repo root resolution ─────────────────────────────────────────────────────
# Locates the `dart_smb2` Flutter package this build infrastructure targets.
# Build outputs (libraries, generated Dart sources, fixtures) all land under
# the repo root resolved here.
#
# Self-locating + depth-agnostic: walks up the directory tree from this
# file's location, at each ancestor checking for a sibling `dart_smb2/`.
#
# Resolution order:
#   1. $DART_SMB2_ROOT — explicit override (used by Docker runs where /repo
#                       is bind-mounted).
#   2. Walk up from <helpers_dir>; at each ancestor check for a sibling
#      `dart_smb2/` whose pubspec.yaml has `name: dart_smb2`.
#   3. Walk up from <helpers_dir>; at each ancestor check the directory
#      itself (legacy nested layout, when this infrastructure used to live
#      inside `dart_smb2/scripts/`).
#
# Errors out with an actionable message when no candidate is valid.
resolve_repo_root() {
  local helpers_dir
  helpers_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local candidate

  if [[ -n "${DART_SMB2_ROOT:-}" ]]; then
    candidate="$DART_SMB2_ROOT"
    _validate_repo_root "$candidate" "DART_SMB2_ROOT" || return 1
    (cd "$candidate" && pwd)
    return 0
  fi

  # Walk up looking for a sibling `dart_smb2/` (production layout).
  local search="$helpers_dir"
  while [[ "$search" != "/" ]]; do
    candidate="$search/../dart_smb2"
    if [[ -f "$candidate/pubspec.yaml" ]] && \
       grep -q "^name: dart_smb2" "$candidate/pubspec.yaml" 2>/dev/null; then
      (cd "$candidate" && pwd)
      return 0
    fi
    search="$(dirname "$search")"
  done

  # Walk up looking for an ancestor that IS the dart_smb2 checkout
  # (legacy layout, scripts nested inside the package).
  search="$helpers_dir"
  while [[ "$search" != "/" ]]; do
    if [[ -f "$search/pubspec.yaml" ]] && \
       grep -q "^name: dart_smb2" "$search/pubspec.yaml" 2>/dev/null; then
      (cd "$search" && pwd)
      return 0
    fi
    search="$(dirname "$search")"
  done

  echo "ERROR: cannot locate the dart_smb2 repo." >&2
  echo "Tried walking up from $helpers_dir:" >&2
  echo "  - looking for a sibling dart_smb2/ at every ancestor" >&2
  echo "  - looking for a dart_smb2 ancestor (legacy nested layout)" >&2
  echo "" >&2
  echo "Set DART_SMB2_ROOT=/absolute/path/to/dart_smb2" >&2
  return 1
}

_validate_repo_root() {
  local path="$1" source="$2"
  if [[ ! -d "$path" ]]; then
    echo "ERROR: $source points at a non-existent path: $path" >&2
    return 1
  fi
  if [[ ! -f "$path/pubspec.yaml" ]]; then
    echo "ERROR: $source does not contain pubspec.yaml: $path" >&2
    return 1
  fi
  if ! grep -q "^name: dart_smb2" "$path/pubspec.yaml" 2>/dev/null; then
    echo "ERROR: $source pubspec.yaml is not the dart_smb2 package: $path" >&2
    return 1
  fi
  return 0
}

# ── libsmb2-scripts repo root ────────────────────────────────────────────────
# Self-locating: this file lives at <repo>/scripts/shared/_helpers.sh, so the
# repo root is two levels up. Used to anchor release_builds/, src/, docker/,
# etc. (all top-level under libsmb2-scripts/).
LIBSMB2_SCRIPTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LIBSMB2_SCRIPTS_ROOT

# ── Upstream source fetch + patch ────────────────────────────────────────────
# prepare_libsmb2_sources <build_dir>
#
# Materializes a patched libsmb2 source tree for one platform build:
#   1. Downloads the pinned GitHub codeload tarball into sources/cache/
#      (skipped when already present), verifying its SHA-256.
#   2. Extracts a FRESH copy into <build_dir>/libsmb2-src — patches are
#      applied per-build so the cache stays pristine.
#   3. Installs the static config header (scripts/shared/config/config.h).
#   4. Runs every patches/libsmb2/shared/patch_*.py, then the platform
#      overlay patches/libsmb2/$PATCH_PLATFORM/patch_*.py when set.
#
# Requires _versions.sh to be sourced first. Sets SMB2_SRC to the patched
# source root on return.
prepare_libsmb2_sources() {
  local build_dir="$1"
  local cache_dir="$LIBSMB2_SCRIPTS_ROOT/sources/cache"
  local tarball="$cache_dir/libsmb2-${LIBSMB2_COMMIT}.tar.gz"
  local url="https://github.com/sahlberg/libsmb2/archive/${LIBSMB2_COMMIT}.tar.gz"

  mkdir -p "$cache_dir"

  if [ ! -f "$tarball" ] || [ "${FORCE_DOWNLOAD:-0}" = "1" ]; then
    echo "  Fetching libsmb2 @ ${LIBSMB2_COMMIT:0:12}..."
    curl -fsSL "$url" -o "$tarball.tmp"
    mv "$tarball.tmp" "$tarball"
  fi

  local sum
  sum="$(sha256sum "$tarball" 2>/dev/null | cut -d' ' -f1)" \
    || sum="$(shasum -a 256 "$tarball" | cut -d' ' -f1)"
  if [ "$sum" != "$LIBSMB2_TARBALL_SHA256" ]; then
    echo "ERROR: libsmb2 tarball SHA-256 mismatch:" >&2
    echo "  expected $LIBSMB2_TARBALL_SHA256" >&2
    echo "  got      $sum" >&2
    echo "Delete $tarball and retry, or update LIBSMB2_TARBALL_SHA256 after a bump." >&2
    return 1
  fi

  export SMB2_SRC="$build_dir/libsmb2-src"
  rm -rf "$SMB2_SRC"
  mkdir -p "$SMB2_SRC"
  tar xzf "$tarball" -C "$SMB2_SRC" --strip-components=1

  cp "$LIBSMB2_SCRIPTS_ROOT/scripts/shared/config/config.h" "$SMB2_SRC/include/config.h"

  local patch_dirs=("$LIBSMB2_SCRIPTS_ROOT/patches/libsmb2/shared")
  if [ -n "${PATCH_PLATFORM:-}" ]; then
    patch_dirs+=("$LIBSMB2_SCRIPTS_ROOT/patches/libsmb2/$PATCH_PLATFORM")
  fi

  local p
  for dir in "${patch_dirs[@]}"; do
    [ -d "$dir" ] || continue
    for p in "$dir"/patch_*.py; do
      [ -e "$p" ] || continue
      echo "  Applying $(basename "$p")..."
      python3 "$p" "$SMB2_SRC"
    done
  done
}
