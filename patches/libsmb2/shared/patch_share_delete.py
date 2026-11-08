# Copyright (c) 2026 & onwards.
# Use of this source code is governed by BSD 3-Clause license.

"""Allow ordinary file opens to be shared for delete/rename.

libsmb2's generic open helper currently requests FILE_SHARE_READ and
FILE_SHARE_WRITE only. If the network disappears while a write handle is
open, Samba may keep the old server-side handle alive until the stale
session times out. A fresh connection can then continue the upload, but a
rename of the completed .part file fails with STATUS_SHARING_VIOLATION.

Add SMB2_FILE_SHARE_DELETE to the generic open request so a stale ordinary
file handle does not block a later rename/delete from another SMB session.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""

import os
import sys

root = sys.argv[1]
fn = os.path.join(root, "lib/libsmb2.c")

with open(fn) as f:
    content = f.read()

old = (
    "        req->share_access = SMB2_FILE_SHARE_READ | SMB2_FILE_SHARE_WRITE;\n"
)

new = (
    "        req->share_access = SMB2_FILE_SHARE_READ | SMB2_FILE_SHARE_WRITE |\n"
    "                SMB2_FILE_SHARE_DELETE;\n"
)

if content.count(old) != 1:
    print(
        "ERROR: generic open share_access anchor not found exactly once "
        "in lib/libsmb2.c (upstream drifted?)"
    )
    sys.exit(1)

content = content.replace(old, new, 1)

with open(fn, "w") as f:
    f.write(content)

print(
    "Patched lib/libsmb2.c: generic file opens allow FILE_SHARE_DELETE"
)