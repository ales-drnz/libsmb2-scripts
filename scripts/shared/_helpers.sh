# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Shared helpers for the build_libsmb2_<platform>.sh scripts.
# Sourced by every script. Do not run directly.

# ── libsmb2-scripts repo root ────────────────────────────────────────────────
# Self-locating: this file lives at <repo>/scripts/shared/_helpers.sh, so the
# repo root is two levels up. Used to anchor release_builds/, sources/ and
# patches/.
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

# ── Shared compile + link pieces ─────────────────────────────────────────────
# Every platform compiles the same sources with the same flags; only the
# compiler, the target flags and the link step differ.

# libsmb2_sources — sets SOURCES to every lib/*.c of the patched tree except
# the Kerberos wrapper (no GSSAPI here). Call after prepare_libsmb2_sources.
libsmb2_sources() {
  SOURCES=()
  local f
  for f in "$SMB2_SRC"/lib/*.c; do
    case "$(basename "$f")" in
      krb5-wrapper.c) continue ;;
      *) SOURCES+=("$f") ;;
    esac
  done
  LIBSMB2_INCLUDES=(
    "-I$SMB2_SRC/include"
    "-I$SMB2_SRC/include/smb2"
    "-I$SMB2_SRC/lib"
  )
  # -w: upstream's own warnings (mostly unused parameters) are not ours to
  # fix and would bury anything the patches introduce in the build log.
  LIBSMB2_CFLAGS=(-O2 -DHAVE_CONFIG_H=1 -fPIC -w)
}

# compile_objects <out_dir> <cc...> -- <flags...>
# Compiles SOURCES into <out_dir>/<name>.o, JOBS compilers at a time. The
# compiler may be several words (`xcrun clang`); `--` ends it. Waits on each
# PID so a failing compile stops the build, and avoids `wait -n`, which the
# bash 3.2 that macOS ships does not have.
compile_objects() {
  local out="$1"; shift
  local cc=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do cc+=("$1"); shift; done
  [ "$#" -gt 0 ] && shift
  local jobs="${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo 4)}"
  mkdir -p "$out"
  local pids=() status=0 src pid
  for src in "${SOURCES[@]}"; do
    "${cc[@]}" -c "$src" "${LIBSMB2_INCLUDES[@]}" "${LIBSMB2_CFLAGS[@]}" "$@" \
      -o "$out/$(basename "${src%.c}").o" &
    pids+=($!)
    if [ "${#pids[@]}" -ge "$jobs" ]; then
      for pid in "${pids[@]}"; do wait "$pid" || status=1; done
      pids=()
    fi
  done
  for pid in "${pids[@]+"${pids[@]}"}"; do wait "$pid" || status=1; done
  [ "$status" -eq 0 ] || { echo "error: compilation failed" >&2; return 1; }
}

# write_export_lists <dir>
# Turns upstream's lib/libsmb2.syms (every public function, plus the
# patched-in smb2_utimes family) into the three linker formats, so each
# binary exports libsmb2's public API and nothing else:
#   <dir>/exports.ver  ELF version script (Linux, Android)
#   <dir>/exports.def  module-definition file (Windows)
#   <dir>/exports.txt  exported-symbols list (Apple, leading underscore)
write_export_lists() {
  local dir="$1" syms="$SMB2_SRC/lib/libsmb2.syms"
  [ -f "$syms" ] || { echo "error: $syms not found" >&2; return 1; }
  mkdir -p "$dir"
  {
    echo "{"
    echo "  global:"
    sed -e '/^[[:space:]]*$/d' -e 's/.*/    &;/' "$syms"
    echo "  local: *;"
    echo "};"
  } > "$dir/exports.ver"
  { echo "EXPORTS"; sed -e '/^[[:space:]]*$/d' -e 's/^/    /' "$syms"; } > "$dir/exports.def"
  sed -e '/^[[:space:]]*$/d' -e 's/^/_/' "$syms" > "$dir/exports.txt"
}
