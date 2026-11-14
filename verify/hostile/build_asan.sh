#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
#
# ASan + UBSan build of the pinned, patched libsmb2 (the tree a release build
# compiles: prepare_libsmb2_sources, shared patches, the build's config.h) as
# a static library, and of harness.c against it. Host compiler (CC, clang by
# default) and the SYSTEM libcrypto, not the pinned static one.
#
#   verify/hostile/build_asan.sh <out_dir>      (outside the repository)
#
# Leaves <out_dir>/tree/libsmb2-src (patched), <out_dir>/pristine (upstream,
# to tell upstream code from patched code), <out_dir>/asan/harness and
# <out_dir>/plain/harness (the release flags, no sanitizer).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:?usage: build_asan.sh <out_dir>}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
source "$ROOT/scripts/shared/_helpers.sh"
source "$ROOT/scripts/shared/_versions.sh"
CC="${CC:-clang}"
JOBS="${JOBS:-4}"

prepare_libsmb2_sources "$OUT/tree" >/dev/null
extract_tarball "$ROOT/sources/cache/libsmb2-${LIBSMB2_COMMIT}.tar.gz" "$OUT/pristine"
SRC="$OUT/tree/libsmb2-src"
INC=(-DHAVE_CONFIG_H=1 -fPIC -w "-I$SRC/include" "-I$SRC/include/smb2" "-I$SRC/lib")

build() { # <name> <flags...>
  local name="$1"; shift
  local dir="$OUT/$name" pids=() f b p
  mkdir -p "$dir/obj"
  for f in "$SRC"/lib/*.c; do
    b="$(basename "${f%.c}")"; [ "$b" = krb5-wrapper ] && continue
    "$CC" -c "$f" "${INC[@]}" "$@" -o "$dir/obj/$b.o" & pids+=($!)
    if [ "${#pids[@]}" -ge "$JOBS" ]; then for p in "${pids[@]}"; do wait "$p"; done; pids=(); fi
  done
  for p in "${pids[@]+"${pids[@]}"}"; do wait "$p"; done
  rm -f "$dir/libsmb2.a"; ar rcs "$dir/libsmb2.a" "$dir"/obj/*.o
  "$CC" "${INC[@]}" "$@" "$HERE/harness.c" "$dir/libsmb2.a" -lcrypto -o "$dir/harness"
  echo "built $dir/harness"
}
build asan -fsanitize=address,undefined -fno-sanitize-recover=undefined -g -O1 -fno-omit-frame-pointer
build plain -O2 -g -fstack-protector-strong -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=2
