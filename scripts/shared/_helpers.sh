# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# Shared helpers for the build_libsmb2_<platform>.sh scripts.
# Sourced by every script. Do not run directly.

# Globs (sources, objects to link) sort by the locale's collation, and the
# link order lands in the binary: pin it so every machine links the same.
export LC_ALL=C

# ── libsmb2-scripts repo root ────────────────────────────────────────────────
# Self-locating: this file lives at <repo>/scripts/shared/_helpers.sh, so the
# repo root is two levels up. Used to anchor release_builds/, sources/ and
# patches/.
LIBSMB2_SCRIPTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LIBSMB2_SCRIPTS_ROOT

# ── Pinned tarballs ─────────────────────────────────────────────────────────
# fetch_verified_tarball <name> <url> <tarball> <expected sha256> <sha var>
#
# Downloads <url> to <tarball> in sources/cache/ unless it is already there
# (FORCE_DOWNLOAD=1 fetches it again), over HTTPS only, and checks its
# SHA-256 against <expected sha256>. <name> labels the messages and <sha var>
# names the _versions.sh variable to update after a bump.
fetch_verified_tarball() {
  local name="$1" url="$2" tarball="$3" expected="$4" sha_var="$5"

  mkdir -p "$(dirname "$tarball")"
  if [ ! -f "$tarball" ] || [ "${FORCE_DOWNLOAD:-0}" = "1" ]; then
    echo "  Fetching $name..."
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 "$url" -o "$tarball.tmp" \
      && mv "$tarball.tmp" "$tarball" \
      || { rm -f "$tarball.tmp"; echo "ERROR: could not download $url" >&2; return 1; }
  fi

  local sum
  sum="$(sha256sum "$tarball" 2>/dev/null | cut -d' ' -f1)" \
    || sum="$(shasum -a 256 "$tarball" | cut -d' ' -f1)"
  if [ "$sum" != "$expected" ]; then
    echo "ERROR: ${name%% *} tarball SHA-256 mismatch:" >&2
    echo "  expected $expected" >&2
    echo "  got      $sum" >&2
    echo "Delete $tarball and retry, or update $sha_var after a bump." >&2
    return 1
  fi
}

# extract_tarball <tarball> <dir>: a fresh copy of the tree in <dir>.
extract_tarball() {
  rm -rf "$2"
  mkdir -p "$2"
  tar xzf "$1" -C "$2" --strip-components=1
}

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
  local tarball="$LIBSMB2_SCRIPTS_ROOT/sources/cache/libsmb2-${LIBSMB2_COMMIT}.tar.gz"

  fetch_verified_tarball "libsmb2 @ ${LIBSMB2_COMMIT:0:12}" \
    "https://github.com/sahlberg/libsmb2/archive/${LIBSMB2_COMMIT}.tar.gz" \
    "$tarball" "$LIBSMB2_TARBALL_SHA256" LIBSMB2_TARBALL_SHA256 || return 1

  export SMB2_SRC="$build_dir/libsmb2-src"
  extract_tarball "$tarball" "$SMB2_SRC"

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

# ── OpenSSL (libcrypto) ──────────────────────────────────────────────────────
# prepare_openssl_sources <build_dir>
#
# Downloads the pinned OpenSSL tarball into sources/cache/ (skipped when
# already there), checks its SHA-256 and extracts it into
# <build_dir>/openssl-src. Each architecture then builds out of tree with
# build_libcrypto, so one extracted copy serves them all. Sets OPENSSL_SRC.
prepare_openssl_sources() {
  local build_dir="$1"
  local tarball="$LIBSMB2_SCRIPTS_ROOT/sources/cache/openssl-${OPENSSL_VERSION}.tar.gz"

  fetch_verified_tarball "OpenSSL ${OPENSSL_VERSION}" \
    "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" \
    "$tarball" "$OPENSSL_TARBALL_SHA256" OPENSSL_TARBALL_SHA256 || return 1

  export OPENSSL_SRC="$build_dir/openssl-src"
  extract_tarball "$tarball" "$OPENSSL_SRC"
}

# The Configure options every libcrypto is built with: a static library
# with only what libsmb2's EVP calls need around it — no shared library,
# engines, loadable modules or legacy provider, no apps, tests or docs, and
# no config file read at startup. -fPIC, as it lands in a shared library.
OPENSSL_CONFIGURE_OPTIONS=(
  no-shared no-module no-dso no-engine no-legacy no-deprecated
  no-apps no-tests no-docs no-ui-console no-autoload-config no-comp
  no-async no-ssl-trace no-filenames
  # Algorithms libsmb2 never asks for: the default provider links in every
  # one it is built with, so each one left out shrinks the library.
  no-aria no-bf no-blake2 no-camellia no-cast no-chacha no-cmp no-cms
  no-ct no-des no-dh no-dsa no-ec no-ecx no-idea no-md4 no-mdc2 no-ocb
  no-ocsp no-poly1305 no-rc2 no-rc4 no-rmd160 no-scrypt no-seed no-siphash
  no-sm2 no-sm3 no-sm4 no-srp no-ts no-whirlpool no-argon2 no-ml-dsa
  no-ml-kem no-slh-dsa
  -fPIC
)

# build_libcrypto <out_dir> <Configure target> [Configure options...]
#
# Builds libcrypto.a for one architecture in <out_dir> from OPENSSL_SRC,
# with the compiler and tools the caller exports (CC, AR, RANLIB, ...).
# Leaves <out_dir>/libcrypto.a and the generated headers in
# <out_dir>/include, and sets OPENSSL_INCLUDES (generated headers first,
# then the source tree's) and LIBCRYPTO for the compile and link steps.
#
# SOURCE_DATE_EPOCH pins the build date OpenSSL records in the library, so
# the same sources give the same bytes.
build_libcrypto() {
  local out="$1" target="$2"; shift 2
  local jobs="${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo 4)}"
  rm -rf "$out"
  mkdir -p "$out"
  echo "  Configuring OpenSSL ${OPENSSL_VERSION} ($target)..."
  (
    cd "$out"
    export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1767225600}"
    perl "$OPENSSL_SRC/Configure" "$target" \
      "${OPENSSL_CONFIGURE_OPTIONS[@]}" "$@" > configure.log 2>&1 \
      || { cat configure.log >&2; exit 1; }
    echo "  Building libcrypto ($target)..."
    make -j"$jobs" build_generated > build.log 2>&1 \
      && make -j"$jobs" libcrypto.a >> build.log 2>&1 \
      || { tail -n 60 build.log >&2; exit 1; }
  )
  OPENSSL_INCLUDES=("-I$out/include" "-I$OPENSSL_SRC/include")
  LIBCRYPTO="$out/libcrypto.a"
  [ -f "$LIBCRYPTO" ] || { echo "error: $LIBCRYPTO was not built" >&2; return 1; }
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

# zip_xcframework <output dir> <zip name>
# Zips <output dir>/libsmb2.xcframework with licenses/libsmb2/ (libsmb2's
# COPYING and the LGPL-2.1 text) and licenses/openssl/ (OpenSSL's
# Apache-2.0 LICENSE.txt) beside it, so the archive carries the licences of
# the code it holds, then removes the xcframework.
#
# The same files give the same zip: the slices in Info.plist sorted, entries in byte order, every time set
# to SOURCE_DATE_EPOCH in UTC, no extra attributes (-X), symlinks kept as
# links (-y). Without this the time of the build and of the checkout ends
# up in the archive and its SHA-256 changes on every run.
zip_xcframework() {
  local dir="$1" name="$2"
  local epoch="${SOURCE_DATE_EPOCH:-1767225600}" stamp
  # BSD date reads an epoch with -r; GNU date with -d @.
  stamp="$(TZ=UTC date -r "$epoch" +%Y%m%d%H%M.%S 2>/dev/null \
    || TZ=UTC date -d "@$epoch" +%Y%m%d%H%M.%S)"
  # xcodebuild -create-xcframework lists the slices in Info.plist in no
  # fixed order; sort them by identifier.
  python3 - "$dir/libsmb2.xcframework/Info.plist" <<'PY'
import plistlib, sys
path = sys.argv[1]
with open(path, 'rb') as f:
    info = plistlib.load(f)
info['AvailableLibraries'].sort(key=lambda lib: lib['LibraryIdentifier'])
with open(path, 'wb') as f:
    plistlib.dump(info, f, sort_keys=True)
PY
  rm -rf "$dir/licenses" "$dir/$name"
  mkdir -p "$dir/licenses"
  cp -R "$LIBSMB2_SCRIPTS_ROOT/licenses/libsmb2" "$LIBSMB2_SCRIPTS_ROOT/licenses/openssl" "$dir/licenses/"
  (
    cd "$dir"
    find libsmb2.xcframework licenses -exec env TZ=UTC touch -h -t "$stamp" {} +
    find libsmb2.xcframework licenses | LC_ALL=C sort \
      | TZ=UTC zip -X -y -q "$name" -@
  )
  rm -rf "$dir/libsmb2.xcframework" "$dir/licenses"
}
