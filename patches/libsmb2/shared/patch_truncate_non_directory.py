# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Make truncate fail on a directory.

smb2_truncate_async() opens the path for writing with no create options,
sets FileEndOfFileInformation and closes it. On a directory the server
grants the open, and the compound succeeded without changing anything, so
truncate() of a directory returned 0 (posix truncate() fails with EISDIR).

The open now carries FILE_NON_DIRECTORY_FILE, so a directory fails with
STATUS_FILE_IS_A_DIRECTORY (-EPERM, libsmb2's errno for that status), as
unlink does (patch_unlink_non_directory.py).
smb2_ftruncate() works on a handle the caller opened and is unchanged.

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
    "        cr_req.create_disposition = SMB2_FILE_OPEN;\n"
    "        cr_req.create_options = 0;\n"
    "        cr_req.name = path;\n"
    "\n"
    "        pdu = smb2_cmd_create_async(smb2, &cr_req, trunc_cb_1, trunc_data);\n"
)
new = (
    "        cr_req.create_disposition = SMB2_FILE_OPEN;\n"
    "        /* dart_smb2: truncate() of a directory fails with\n"
    "         * STATUS_FILE_IS_A_DIRECTORY (see patch_truncate_non_directory.py). */\n"
    "        cr_req.create_options = SMB2_FILE_NON_DIRECTORY_FILE;\n"
    "        cr_req.name = path;\n"
    "\n"
    "        pdu = smb2_cmd_create_async(smb2, &cr_req, trunc_cb_1, trunc_data);\n"
)
if content.count(old) != 1:
    print("ERROR: smb2_truncate_async create_options anchor not found exactly once in lib/libsmb2.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/libsmb2.c: truncate opens with FILE_NON_DIRECTORY_FILE")
