# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Add smb2_scripts_release() — the libsmb2-scripts release of the library.

Every version of dart_smb2 drives the libsmb2 of the release it pins and no
other: the patched API it binds, the errors it maps and the behaviour its
tests hold are those of that release. Upstream libsmb2 has no version call,
and a build of this repo looks like any other libsmb2 from the outside, so a
library of another release, or of upstream, could only fail later in ways
that look like bugs.

smb2_scripts_release() returns LIBSMB2_RELEASE (scripts/shared/_versions.sh,
e.g. "r11"), the release the binaries ship as (libsmb2-<release>), baked in
when the tree is patched. dart_smb2 calls it before its first context and
refuses a library that lacks it or names another release. The string is the
same on every platform and holds no date or path, so builds stay
reproducible.

Touches:
  include/smb2/libsmb2.h        — declaration
  lib/smb2-scripts-release.c    — new file, the definition
  lib/libsmb2.syms              — export list entry

The release comes from the LIBSMB2_RELEASE environment variable, which
_versions.sh exports before the patches run.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import re
import sys

root = sys.argv[1]

release = os.environ.get("LIBSMB2_RELEASE", "")
if not re.fullmatch(r"r\d+", release):
    print(f"ERROR: LIBSMB2_RELEASE is {release!r}, expected rN (source scripts/shared/_versions.sh)")
    sys.exit(1)

SOURCE_PATH = "lib/smb2-scripts-release.c"
SOURCE = f"""/*
 * Added by libsmb2-scripts (patches/libsmb2/shared/patch_scripts_release.py).
 *
 * The libsmb2-scripts release this library was built as (libsmb2-<release>).
 */
const char *smb2_scripts_release(void);

const char *smb2_scripts_release(void)
{{
        return "{release}";
}}
"""

# Already applied (a second run on the same tree): nothing to do, unless it
# was applied for another release.
with open(os.path.join(root, "include/smb2/libsmb2.h")) as f:
    if "smb2_scripts_release" in f.read():
        with open(os.path.join(root, SOURCE_PATH)) as f:
            if f.read() != SOURCE:
                print(f"ERROR: tree already patched for another release than {release}")
                sys.exit(1)
        print("Already patched: smb2_scripts_release")
        sys.exit(0)

# Every edit is applied to an in-memory copy first and the files are written
# only once all of them matched, so a drifted anchor leaves the tree as it
# was instead of half-patched.
files = {}


def patch(relpath, old, new):
    if relpath not in files:
        with open(os.path.join(root, relpath)) as f:
            files[relpath] = f.read()
    content = files[relpath]
    if content.count(old) != 1:
        print(f"ERROR: anchor not found exactly once in {relpath} (upstream drifted?)")
        sys.exit(1)
    files[relpath] = content.replace(old, new, 1)


# ── include/smb2/libsmb2.h — public declaration, before smb2_init_context ────
patch(
    "include/smb2/libsmb2.h",
    "/*\n"
    " * Create an SMB2 context.\n",
    "/*\n"
    " * The libsmb2-scripts release this library was built as, e.g. \"r11\"\n"
    " * (libsmb2-<release>). Added by libsmb2-scripts; upstream libsmb2 has\n"
    " * no such call.\n"
    " */\n"
    "const char *smb2_scripts_release(void);\n"
    "\n"
    "/*\n"
    " * Create an SMB2 context.\n",
)

# ── lib/libsmb2.syms — export list, kept in byte order ───────────────────────
patch(
    "lib/libsmb2.syms",
    "\nsmb2_seekdir\n",
    "\nsmb2_scripts_release\nsmb2_seekdir\n",
)

if os.path.exists(os.path.join(root, SOURCE_PATH)):
    print(f"ERROR: {SOURCE_PATH} already exists (upstream drifted?)")
    sys.exit(1)
files[SOURCE_PATH] = SOURCE

for relpath, content in files.items():
    with open(os.path.join(root, relpath), "w") as f:
        f.write(content)

print(f"Patched: smb2_scripts_release() returns \"{release}\" (libsmb2.h, smb2-scripts-release.c, libsmb2.syms)")
