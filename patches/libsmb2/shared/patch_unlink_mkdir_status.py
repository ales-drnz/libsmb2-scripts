# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Record the NT status of a CLOSE that fails in unlink and mkdir.

smb2_unlink_async() and smb2_mkdir_async() send CREATE + CLOSE as one
compound. Since libsmb2 7.0.0 the call data keeps the first failing status
and the caller gets its errno, and create_cb_1() records the status of a
failed CREATE. A CLOSE that failed after a CREATE that succeeded still left
no NT status behind, so smb2_get_nterror() named an earlier, unrelated
failure while the errno named the CLOSE's.

create_cb_2() now records that status when it is the first failure.

ftruncate shares struct create_cb_data and its callbacks are not touched.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

p = Patch(sys.argv[1], sentinel=("lib/libsmb2.c", '"Close failed with status %s.",'))

old = (
    "        struct create_cb_data *create_data = private_data;\n"
    "\n"
    "        if (create_data->status == SMB2_STATUS_SUCCESS) {\n"
    "                create_data->status = status;\n"
    "        }\n"
    "        create_unref(smb2, create_data);\n"
    "}\n"
    "\n"
    "static void\n"
    "create_cb_1(struct smb2_context *smb2, int status,\n"
)
new = (
    "        struct create_cb_data *create_data = private_data;\n"
    "\n"
    "        if (create_data->status == SMB2_STATUS_SUCCESS) {\n"
    "                if (status != SMB2_STATUS_SUCCESS) {\n"
    "                        smb2_set_nterror(smb2, status,\n"
    "                                         \"Close failed with status %s.\",\n"
    "                                         nterror_to_str(status));\n"
    "                }\n"
    "                create_data->status = status;\n"
    "        }\n"
    "        create_unref(smb2, create_data);\n"
    "}\n"
    "\n"
    "static void\n"
    "create_cb_1(struct smb2_context *smb2, int status,\n"
)
p.replace("lib/libsmb2.c", old, new)

p.done("Patched lib/libsmb2.c: unlink and mkdir record the status of a failed CLOSE")
