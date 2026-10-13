#!/usr/bin/env bash
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

# =============================================================================
# write_manifest.sh
#
# Writes release_builds/manifest.json and release_builds/SHA256SUMS, and
# copies libsmb2's licence texts (licenses/libsmb2/COPYING and
# LICENCE-LGPL-2.1.txt) beside them; all of it is published with the
# binaries on the libsmb2-<release> GitHub release. The manifest
# states what the release contains, so consumers never re-derive it from this
# repo's scripts:
#
#   release   the release tag suffix (LIBSMB2_RELEASE, e.g. "r9")
#   libsmb2   the pinned upstream commit, its describe-style version and the
#             SHA-256 of the source tarball
#   source    the libsmb2-scripts commit the binaries were built from (the
#             LGPL corresponding source: upstream tarball + patches/)
#   patches   the patch scripts applied, per platform overlay
#   symbols   the functions every binary is verified to export
#             (verify/symbols.txt)
#   assets    SHA-256 of every binary, keyed by file name
#   licenses  SHA-256 of the licence texts, keyed by file name
#
# SHA256SUMS lists the binaries and the licence texts. dart_smb2's
# tool/update_libsmb2.sh copies the asset hashes into its build hook, and
# tool/bindings_drift.dart wants every entry of `assets` pinned there: the
# licence texts stay out of `assets`, which lists the binaries only, as dart_smb2's
# tool/update_libsmb2.sh and bindings_drift.dart expect.
#
# It fails unless release_builds/ holds exactly the nine release assets, so
# a partial build (or a stale binary left from an earlier one) never gets a
# manifest that looks complete. ALLOW_PARTIAL=1 writes one for whatever
# subset is there, with a warning; an unexpected libsmb2_* file is always an
# error.
#
# Usage (from the repo root): scripts/write_manifest.sh
# RELEASE_DIR overrides the directory it reads and writes; SOURCE_COMMIT
# overrides the recorded libsmb2-scripts commit (CI passes $GITHUB_SHA).
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shared/_versions.sh"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RELEASE_DIR="${RELEASE_DIR:-$ROOT/release_builds}"
[ -d "$RELEASE_DIR" ] || { echo "No release directory: $RELEASE_DIR" >&2; exit 1; }

for f in COPYING LICENCE-LGPL-2.1.txt; do
  cp "$ROOT/licenses/libsmb2/$f" "$RELEASE_DIR/$f"
done

SOURCE_COMMIT="${SOURCE_COMMIT:-$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)}"
if [ -z "${SOURCE_COMMIT_ALLOW_DIRTY:-}" ] && [ -n "$(git -C "$ROOT" status --porcelain -- patches scripts docker 2>/dev/null)" ]; then
  echo "warning: patches/, scripts/ or docker/ have uncommitted changes;" >&2
  echo "         the manifest's source commit does not describe these binaries." >&2
fi

RELEASE_DIR="$RELEASE_DIR" ROOT="$ROOT" SOURCE_COMMIT="$SOURCE_COMMIT" \
  ALLOW_PARTIAL="${ALLOW_PARTIAL:-0}" python3 - <<'PY'
import hashlib, json, os, pathlib, sys

root = pathlib.Path(os.environ["ROOT"])
release_dir = pathlib.Path(os.environ["RELEASE_DIR"])

# The nine release assets (verify_binaries.sh checks the same set).
EXPECTED = [
    "libsmb2_android-arm64-v8a.so",
    "libsmb2_android-armeabi-v7a.so",
    "libsmb2_android-x86_64.so",
    "libsmb2_ios.xcframework.zip",
    "libsmb2_linux-aarch64.so",
    "libsmb2_linux-x86_64.so",
    "libsmb2_macos.xcframework.zip",
    "libsmb2_windows-arm64.dll",
    "libsmb2_windows-x86_64.dll",
]

found = sorted(
    f.name for f in release_dir.iterdir()
    if f.is_file() and f.name.startswith("libsmb2_")
)
unexpected = [n for n in found if n not in EXPECTED]
missing = [n for n in EXPECTED if n not in found]
if unexpected:
    raise SystemExit(f"Unexpected files in {release_dir}: {', '.join(unexpected)}")
if not found:
    raise SystemExit(f"No libsmb2_* binaries in {release_dir}")
if missing:
    if os.environ["ALLOW_PARTIAL"] != "1":
        raise SystemExit(
            f"{len(found)} of the {len(EXPECTED)} release assets in {release_dir}; "
            f"missing: {', '.join(missing)}.\n"
            "Build them (CI builds all nine), or set ALLOW_PARTIAL=1 for a "
            "manifest of this subset only."
        )
    bar = "!" * 72
    print(f"{bar}\nWARNING: ALLOW_PARTIAL=1: this manifest lists {len(found)} of the "
          f"{len(EXPECTED)} release assets\nand is NOT a release. Missing: "
          f"{', '.join(missing)}\n{bar}", file=sys.stderr)

assets = {
    name: hashlib.sha256((release_dir / name).read_bytes()).hexdigest()
    for name in found
}
licenses = {
    name: hashlib.sha256((release_dir / name).read_bytes()).hexdigest()
    for name in ("COPYING", "LICENCE-LGPL-2.1.txt")
}

patches = {
    d.name: sorted(p.name for p in d.glob("patch_*.py"))
    for d in sorted((root / "patches" / "libsmb2").iterdir())
    if d.is_dir()
}
symbols = [
    line.strip()
    for line in (root / "verify" / "symbols.txt").read_text().splitlines()
    if line.strip() and not line.startswith("#")
]

manifest = {
    "release": os.environ["LIBSMB2_RELEASE"],
    "libsmb2": {
        "commit": os.environ["LIBSMB2_COMMIT"],
        "version": os.environ["LIBSMB2_VERSION"],
        "tarballSha256": os.environ["LIBSMB2_TARBALL_SHA256"],
    },
    "source": {
        "repository": "https://github.com/ales-drnz/libsmb2-scripts",
        "commit": os.environ["SOURCE_COMMIT"],
    },
    "license": "LGPL-2.1-or-later",
    "patches": patches,
    "symbols": symbols,
    "assets": assets,
    "licenses": licenses,
}
(release_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(release_dir / "SHA256SUMS").write_text(
    "".join(f"{sha}  {name}\n" for name, sha in {**assets, **licenses}.items())
)
print(f"Wrote {release_dir / 'manifest.json'} and SHA256SUMS "
      f"({len(assets)} assets, {len(licenses)} licence texts)")
PY
