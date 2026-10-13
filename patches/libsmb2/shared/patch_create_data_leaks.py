# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Free the call data when the first PDU of unlink, mkdir or ftruncate fails.

smb2_unlink_internal() (unlink, and the symlink cleanup), smb2_mkdir_async()
and smb2_ftruncate_async() allocate their create_cb_data, then build the
first PDU; when that returns NULL they set the error and return -ENOMEM
without freeing it. The later failure paths of the same functions, rmdir
and getinfo free theirs. smb2_cmd_create_async() returns NULL not only when
memory runs out but also when the request cannot be encoded, for instance
a path that is not valid UTF-8, so a caller could leak one allocation per
rejected path.

Each of those returns now frees create_data first.

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
    # smb2_unlink_internal() and smb2_mkdir_async(): the CREATE.
    (
        "        pdu = smb2_cmd_create_async(smb2, &cr_req, create_cb_1, create_data);\n"
        "        if (pdu == NULL) {\n"
        "                smb2_set_error(smb2, \"Failed to create create command\");\n"
        "                return -ENOMEM;\n"
        "        }\n",
        "        pdu = smb2_cmd_create_async(smb2, &cr_req, create_cb_1, create_data);\n"
        "        if (pdu == NULL) {\n"
        "                smb2_set_error(smb2, \"Failed to create create command\");\n"
        "                free(create_data); /* dart_smb2: patch_create_data_leaks.py */\n"
        "                return -ENOMEM;\n"
        "        }\n",
        2,
    ),
    # smb2_ftruncate_async(): the SET_INFO.
    (
        "        pdu = smb2_cmd_set_info_async(smb2, &req, ftrunc_cb_1, create_data);\n"
        "        if (pdu == NULL) {\n"
        "                smb2_set_error(smb2, \"Failed to create set info command\");\n"
        "                return -ENOMEM;\n"
        "        }\n",
        "        pdu = smb2_cmd_set_info_async(smb2, &req, ftrunc_cb_1, create_data);\n"
        "        if (pdu == NULL) {\n"
        "                smb2_set_error(smb2, \"Failed to create set info command\");\n"
        "                free(create_data); /* dart_smb2: patch_create_data_leaks.py */\n"
        "                return -ENOMEM;\n"
        "        }\n",
        1,
    ),
]

for old, new, count in fixes:
    if content.count(old) != count:
        print(f"ERROR: anchor not found {count} time(s) in lib/libsmb2.c (upstream drifted?):")
        print(old)
        sys.exit(1)
    content = content.replace(old, new)

with open(fn, "w") as f:
    f.write(content)
print("Patched lib/libsmb2.c: unlink, mkdir and ftruncate free their call data when the first PDU fails")
