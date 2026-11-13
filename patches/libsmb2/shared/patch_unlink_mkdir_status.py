# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Make unlink and mkdir report the first failure of their compound.

smb2_unlink_async() and smb2_mkdir_async() send CREATE + CLOSE as one
compound. create_cb_1() records the NT status of a failed CREATE (see
patch_nterror_reporting.py), but create_cb_2() gave the caller the errno
of the CLOSE alone. A server answers the CLOSE of a failed CREATE with a
status of its own choice, the CREATE's or STATUS_FILE_CLOSED or
STATUS_INVALID_PARAMETER, so the errno could name another failure than
smb2_get_nterror() did; and a CLOSE that failed after a CREATE that
succeeded left no NT status at all.

The call data now keeps the first failing status, the way rmdir_cb_*
(patch_rmdir_disposition.py) and upstream's stat and rename callbacks do:
the errno is the one of that status, and a failing CLOSE records its own.

ftruncate shares struct create_cb_data and does not read the new field.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

root = sys.argv[1]
fn = os.path.join(root, "lib/libsmb2.c")
with open(fn) as f:
    content = f.read()

fixes = [
    # The call data: the first failing status.
    (
        "struct create_cb_data {\n"
        "        smb2_command_cb cb;\n"
        "        void *cb_data;\n"
        "};\n",
        "struct create_cb_data {\n"
        "        smb2_command_cb cb;\n"
        "        void *cb_data;\n"
        "        /* dart_smb2: the first failure of the compound (see\n"
        "         * patch_unlink_mkdir_status.py). */\n"
        "        uint32_t status;\n"
        "};\n",
    ),
    # The CLOSE: report the first failure, and record its own.
    (
        "        struct create_cb_data *create_data = private_data;\n"
        "\n"
        "        if (status != SMB2_STATUS_SUCCESS) {\n"
        "                status = -nterror_to_errno(status);\n"
        "        }\n"
        "\n"
        "        create_data->cb(smb2, status, NULL, create_data->cb_data);\n"
        "        free(create_data);\n",
        "        struct create_cb_data *create_data = private_data;\n"
        "\n"
        "        if (create_data->status == SMB2_STATUS_SUCCESS &&\n"
        "            status != SMB2_STATUS_SUCCESS) {\n"
        "                create_data->status = status;\n"
        "                smb2_set_nterror(smb2, status,\n"
        "                                 \"Close failed with (0x%08x) %s.\",\n"
        "                                 status, nterror_to_str(status));\n"
        "        }\n"
        "\n"
        "        create_data->cb(smb2, -nterror_to_errno(create_data->status),\n"
        "                        NULL, create_data->cb_data);\n"
        "        free(create_data);\n",
    ),
    # The CREATE: keep its status. Anchored above the line that
    # patch_nterror_reporting.py rewrites, so either may run first.
    (
        "create_cb_1(struct smb2_context *smb2, int status,\n"
        "            void *command_data, void *private_data)\n"
        "{\n"
        "        if (status != SMB2_STATUS_SUCCESS) {\n",
        "create_cb_1(struct smb2_context *smb2, int status,\n"
        "            void *command_data, void *private_data)\n"
        "{\n"
        "        struct create_cb_data *create_data = private_data;\n"
        "\n"
        "        if (create_data->status == SMB2_STATUS_SUCCESS) {\n"
        "                create_data->status = status;\n"
        "        }\n"
        "        if (status != SMB2_STATUS_SUCCESS) {\n",
    ),
]

for old, new in fixes:
    if content.count(old) != 1:
        print("ERROR: anchor not found exactly once in lib/libsmb2.c (upstream drifted?):")
        print(old)
        sys.exit(1)
    content = content.replace(old, new, 1)

with open(fn, "w") as f:
    f.write(content)
print("Patched lib/libsmb2.c: unlink and mkdir report the first failing status of their compound")
