#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
#
# =============================================================================
# check_patches.sh
#
# Checks the patch set against the pinned libsmb2 tree, without building a
# library. For the shared patches alone and for shared + each platform
# overlay (patches/libsmb2/<scope>/):
#
#   1. every patch applies to a fresh tree, in name order and in reverse
#      name order (the overlay still after the shared ones, as in a build);
#   2. a second run of every patch on the patched tree exits 0 and leaves
#      it byte for byte as it was;
#   3. both orders give the same tree.
#
# Then every lib/*.c the shared patches changed or added is compiled with
# the host compiler (CC, cc when unset) and the build's defines, with
# -Wall -Wextra printed (less the four classes upstream's own code trips)
# and the classes of warning that it is free of today turned into errors: an undeclared function, a pointer or
# integer of the wrong type, a missing return, a bad format, an unused or
# uninitialised variable. The overlays' edits are for one toolchain and are
# compiled by that platform's build only.
#
# Needs python3, tar, diff and a C compiler; the pinned tarball is taken
# from sources/cache/ or downloaded there. Nothing outside a temporary
# directory is written.
#
# Usage:
#   ./scripts/check_patches.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_helpers.sh"
source "$SCRIPT_DIR/shared/_versions.sh"

PATCHES="$LIBSMB2_SCRIPTS_ROOT/patches/libsmb2"
TARBALL="$LIBSMB2_SCRIPTS_ROOT/sources/cache/libsmb2-${LIBSMB2_COMMIT}.tar.gz"
CC="${CC:-cc}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "=== libsmb2: checking the patch set against ${LIBSMB2_COMMIT:0:12} ==="
fetch_verified_tarball "libsmb2 @ ${LIBSMB2_COMMIT:0:12}" \
  "https://github.com/sahlberg/libsmb2/archive/${LIBSMB2_COMMIT}.tar.gz" \
  "$TARBALL" "$LIBSMB2_TARBALL_SHA256" LIBSMB2_TARBALL_SHA256

# fresh_tree <dir>: the pinned tree with the build's config.h, unpatched.
fresh_tree() {
  extract_tarball "$TARBALL" "$1"
  cp "$SCRIPT_DIR/shared/config/config.h" "$1/include/config.h"
}

# patch_list <order> <scope>...: the patch scripts of the scopes, one per
# line, each scope's in name order (fwd) or reverse name order (rev).
patch_list() {
  local order="$1" scope p; shift
  for scope in "$@"; do
    for p in "$PATCHES/$scope"/patch_*.py; do
      [ -e "$p" ] && echo "$p"
    done | if [ "$order" = rev ]; then sort -r; else sort; fi
  done
}

# apply_twice <dir> <order> <scope>...
apply_twice() {
  local dir="$1" order="$2" p out; shift 2
  local -a list=()
  while IFS= read -r p; do list+=("$p"); done < <(patch_list "$order" "$@")

  fresh_tree "$dir"
  for p in "${list[@]}"; do
    out="$(LIBSMB2_PATCH_FRESH=1 python3 "$p" "$dir" 2>&1)" || {
      echo "$out" >&2
      echo "FAIL: $(basename "$p") does not apply ($* $order)" >&2
      return 1
    }
  done

  cp -R "$dir" "$dir.once"
  for p in "${list[@]}"; do
    out="$(python3 "$p" "$dir" 2>&1)" || {
      echo "$out" >&2
      echo "FAIL: second run of $(basename "$p") failed ($* $order)" >&2
      return 1
    }
    case "$out" in
      "Already applied: "*) ;;
      *)
        echo "$out" >&2
        echo "FAIL: second run of $(basename "$p") did not see it was applied ($* $order)" >&2
        return 1
        ;;
    esac
  done
  diff -r "$dir.once" "$dir" > "$WORK/diff.txt" || {
    head -n 40 "$WORK/diff.txt" >&2
    echo "FAIL: a second run of the patches changed the tree ($* $order)" >&2
    return 1
  }
  rm -rf "$dir.once"
  echo "  ok: ${#list[@]} patches apply, and a second run changes nothing ($* $order)"
}

# The overlays present, each checked on top of the shared patches.
overlays=()
for d in "$PATCHES"/*/; do
  name="$(basename "$d")"
  [ "$name" = shared ] || overlays+=("$name")
done

n=0
for overlay in "" "${overlays[@]+"${overlays[@]}"}"; do
  n=$((n + 1))
  scopes=(shared)
  [ -z "$overlay" ] || scopes+=("$overlay")
  apply_twice "$WORK/fwd$n" fwd "${scopes[@]}"
  apply_twice "$WORK/rev$n" rev "${scopes[@]}"
  diff -r "$WORK/fwd$n" "$WORK/rev$n" > "$WORK/diff.txt" || {
    head -n 40 "$WORK/diff.txt" >&2
    echo "FAIL: the tree depends on the order of the patches (${scopes[*]})" >&2
    exit 1
  }
  echo "  ok: both orders give the same tree (${scopes[*]})"
done

# ── Compile what the shared patches touched ──────────────────────────────────
fresh_tree "$WORK/pristine"
touched=()
for f in "$WORK/fwd1"/lib/*.c; do
  cmp -s "$f" "$WORK/pristine/lib/$(basename "$f")" || touched+=("$f")
done
[ "${#touched[@]}" -gt 0 ] || { echo "FAIL: the patches changed no lib/*.c" >&2; exit 1; }

echo "=== compiling ${#touched[@]} patched files with $CC ==="
"$CC" --version | head -n 1
failed=0
for f in "${touched[@]}"; do
  echo "  $(basename "$f")"
  "$CC" -c "$f" -o "$WORK/check.o" \
    -O2 -DHAVE_CONFIG_H=1 -fPIC \
    "-I$WORK/fwd1/include" "-I$WORK/fwd1/include/smb2" "-I$WORK/fwd1/lib" \
    -Wall -Wextra -Wno-unused-parameter -Wno-sign-compare \
    -Wno-type-limits -Wno-implicit-fallthrough \
    -Werror=implicit-function-declaration -Werror=implicit-int \
    -Werror=incompatible-pointer-types -Werror=int-conversion \
    -Werror=return-type -Werror=format -Werror=uninitialized \
    -Werror=unused-variable -Werror=unused-function \
    -Werror=unused-but-set-variable \
    || failed=$((failed + 1))
done
[ "$failed" -eq 0 ] || { echo "FAIL: $failed patched file(s) did not compile cleanly" >&2; exit 1; }

echo "OK: the patch set applies, is idempotent, does not depend on its order, and compiles"
