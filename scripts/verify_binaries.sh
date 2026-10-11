#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# verify_binaries.sh
#
# Checks every binary in release_builds/ before it is published. Runs in the
# `verify` stage of docker/Dockerfile (ubuntu:20.04 with binutils and LLVM),
# locally through `./build verify` and in CI.
#
#   all       the nine release assets are present, and each exports every
#             symbol in verify/symbols.txt
#   Linux     ELF machine per arch; no glibc symbol newer than 2.31; the
#             host-arch library is dlopened on this glibc 2.31 system, its
#             symbols resolved and a context created and destroyed
#   Android   ELF machine per ABI; 16 KB segment alignment on the 64-bit ABIs;
#             depends on nothing but libc / libdl / libm
#   Windows   PE machine per arch; imports only system DLLs (kernel32,
#             ws2_32, bcrypt, the UCRT api sets)
#   Apple     slices per xcframework; LC_BUILD_VERSION minimum OS within the
#             floor (iOS 13.0, macOS 10.15; arm64-only slices are raised to
#             what that arch requires: simulator 14.0, macOS 11.0); the macOS
#             framework keeps its Versions/Current symlinks
#
# Usage (from the repo root): scripts/verify_binaries.sh
# RELEASE_DIR overrides the directory it reads.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE_DIR="${RELEASE_DIR:-$ROOT/release_builds}"
SYMBOLS="$ROOT/verify/symbols.txt"

for tool in readelf objdump llvm-objdump llvm-nm llvm-lipo unzip cc; do
  command -v "$tool" >/dev/null || {
    echo "verify: $tool not found — run inside the docker/Dockerfile verify stage (./build verify)." >&2
    exit 1
  }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cc -O0 "$ROOT/verify/dlopen_test.c" -o "$WORK/dlopen_test" -ldl

failed=0
fail() { echo "FAIL $*"; failed=$((failed + 1)); }
ok() { echo "OK   $*"; }

required_symbols() { grep -v -e '^#' -e '^[[:space:]]*$' "$SYMBOLS"; }

# check_exports <label> <file with one exported name per line>
check_exports() {
  local label="$1" exported="$2" missing
  missing="$(required_symbols | sort | comm -23 - <(sort -u "$exported"))"
  if [ -n "$missing" ]; then
    fail "$label: missing exports: $(echo "$missing" | tr '\n' ' ')"
  else
    ok "$label: exports all $(required_symbols | wc -l) bound symbols"
  fi
}

elf_machine() { readelf -hW "$1" | sed -n 's/^ *Machine: *//p'; }

# version_le A B — A <= B for dotted versions
version_le() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]; }

asset() {
  local f="$RELEASE_DIR/$1"
  if [ -f "$f" ]; then echo "$f"; else fail "$1: not found in $RELEASE_DIR"; echo ""; fi
}

# ── Linux ────────────────────────────────────────────────────────────────────
for arch in x86_64 aarch64; do
  name="libsmb2_linux-$arch.so"
  f="$(asset "$name")"; [ -n "$f" ] || continue
  case "$arch:$(elf_machine "$f")" in
    x86_64:*X86-64*|aarch64:*AArch64*) ;;
    *) fail "$name: wrong ELF machine ($(elf_machine "$f"))" ;;
  esac
  newest="$(objdump -T "$f" | grep -o 'GLIBC_[0-9.]*' | sed 's/GLIBC_//' | sort -uV | tail -1)"
  if version_le "${newest:-0}" 2.31; then
    ok "$name: newest glibc symbol ${newest:-none} (floor 2.31)"
  else
    fail "$name: needs glibc $newest, above the 2.31 floor"
  fi
  nm -D --defined-only "$f" | awk '{print $NF}' > "$WORK/exports"
  check_exports "$name" "$WORK/exports"
  if [ "$(uname -m)" = "$arch" ]; then
    "$WORK/dlopen_test" "$f" "$SYMBOLS" || failed=$((failed + 1))
  else
    echo "SKIP $name: dlopen needs an $arch host"
  fi
done

# ── Android ──────────────────────────────────────────────────────────────────
for abi in arm64-v8a armeabi-v7a x86_64; do
  name="libsmb2_android-$abi.so"
  f="$(asset "$name")"; [ -n "$f" ] || continue
  machine="$(elf_machine "$f")"
  case "$abi:$machine" in
    arm64-v8a:*AArch64*|armeabi-v7a:ARM|x86_64:*X86-64*) ;;
    *) fail "$name: wrong ELF machine ($machine)" ;;
  esac
  if [ "$abi" != "armeabi-v7a" ]; then
    align="$(readelf -lW "$f" | awk '/LOAD/ {print $NF}' | sort -u)"
    for a in $align; do
      if [ $((a)) -lt 16384 ]; then fail "$name: LOAD alignment $a below 16 KB"; fi
    done
    ok "$name: LOAD alignment $(echo "$align" | tr '\n' ' ')"
  fi
  needed="$(readelf -dW "$f" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | sort -u | tr '\n' ' ')"
  for lib in $needed; do
    case "$lib" in
      libc.so|libdl.so|libm.so) ;;
      *) fail "$name: unexpected dependency $lib" ;;
    esac
  done
  ok "$name: depends on $needed"
  llvm-nm -D --defined-only "$f" | awk '{print $NF}' > "$WORK/exports"
  check_exports "$name" "$WORK/exports"
done

# ── Windows ──────────────────────────────────────────────────────────────────
for arch in x86_64 arm64; do
  name="libsmb2_windows-$arch.dll"
  f="$(asset "$name")"; [ -n "$f" ] || continue
  format="$(llvm-objdump -f "$f" | sed -n 's/.*file format //p' | tr '[:upper:]' '[:lower:]')"
  case "$arch:$format" in
    x86_64:coff-x86-64|arm64:coff-arm64) ;;
    *) fail "$name: wrong PE machine ($format)" ;;
  esac
  imports="$(llvm-objdump -p "$f" | sed -n 's/.*DLL Name: //p' | sort -u)"
  for dll in $imports; do
    case "$(echo "$dll" | tr '[:upper:]' '[:lower:]')" in
      kernel32.dll|ws2_32.dll|bcrypt.dll|api-ms-win-crt-*.dll) ;;
      *) fail "$name: unexpected import $dll" ;;
    esac
  done
  ok "$name: imports $(echo "$imports" | grep -vc api-ms-win-crt) system DLLs + the UCRT api sets"
  llvm-objdump -p "$f" | awk '/Export Table:/ {on = 1; next} on && /^ *[0-9]+ +0x/ {print $NF}' > "$WORK/exports"
  check_exports "$name" "$WORK/exports"
done

# ── Apple ────────────────────────────────────────────────────────────────────
# check_slice <label> <binary> <expected archs> <floor> <arm64 floor>
check_slice() {
  local label="$1" bin="$2" want="$3" floor="$4" arm_floor="$5" archs a minos
  archs="$(llvm-lipo -archs "$bin" | tr ' ' '\n' | sed '/^$/d' | sort | tr '\n' ' ')"
  if [ "$archs" != "$want" ]; then
    fail "$label: archs '$archs', expected '$want'"
  fi
  for a in $archs; do
    minos="$(llvm-objdump -macho -private-headers -arch="$a" "$bin" | awk '/LC_BUILD_VERSION/ {on = 1} on && /minos/ {print $2; exit}')"
    local limit="$floor"
    [ "$a" = "arm64" ] && limit="$arm_floor"
    if [ -z "$minos" ] || ! version_le "$minos" "$limit"; then
      fail "$label/$a: minimum OS ${minos:-unknown}, above $limit"
    fi
    llvm-nm -extern-only -defined-only -arch="$a" "$bin" | awk '{print $NF}' | sed 's/^_//' > "$WORK/exports"
    check_exports "$label/$a (minos $minos)" "$WORK/exports"
  done
}

f="$(asset libsmb2_ios.xcframework.zip)"
if [ -n "$f" ]; then
  rm -rf "$WORK/ios" && unzip -q "$f" -d "$WORK/ios"
  xc="$WORK/ios/libsmb2.xcframework"
  check_slice "ios-arm64" "$xc/ios-arm64/libsmb2.framework/libsmb2" "arm64 " 13.0 13.0
  check_slice "ios-simulator" "$xc/ios-arm64_x86_64-simulator/libsmb2.framework/libsmb2" "arm64 x86_64 " 13.0 14.0
fi

f="$(asset libsmb2_macos.xcframework.zip)"
if [ -n "$f" ]; then
  rm -rf "$WORK/macos" && unzip -q "$f" -d "$WORK/macos"
  fw="$WORK/macos/libsmb2.xcframework/macos-arm64_x86_64/libsmb2.framework"
  if [ -L "$fw/Versions/Current" ] && [ -L "$fw/libsmb2" ]; then
    ok "macos: framework symlinks preserved"
  else
    fail "macos: Versions/Current or the top-level libsmb2 symlink is missing"
  fi
  check_slice "macos" "$fw/Versions/A/libsmb2" "arm64 x86_64 " 10.15 11.0
fi

echo ""
if [ "$failed" -eq 0 ]; then
  echo "verify: all checks passed"
else
  echo "verify: $failed check(s) failed"
  exit 1
fi
