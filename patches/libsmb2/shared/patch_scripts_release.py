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

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

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
p = Patch(
    sys.argv[1],
    sentinel=("include/smb2/libsmb2.h", "smb2_scripts_release"),
    exit_if_applied=False,
)
if p.applied:
    if p.on_disk(SOURCE_PATH) != SOURCE:
        p.fail(f"tree already patched for another release than {release}")
    p.exit_applied()

# ── include/smb2/libsmb2.h — public declaration, before smb2_init_context ────
p.replace(
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
p.replace(
    "lib/libsmb2.syms",
    "\nsmb2_seekdir\n",
    "\nsmb2_scripts_release\nsmb2_seekdir\n",
)

p.create(SOURCE_PATH, SOURCE)

p.done(f"Patched: smb2_scripts_release() returns \"{release}\" (libsmb2.h, smb2-scripts-release.c, libsmb2.syms)")
