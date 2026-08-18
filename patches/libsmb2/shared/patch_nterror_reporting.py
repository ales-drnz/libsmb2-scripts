# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Record the NT status string on stat / truncate / create-open failures.

Several high-level callbacks in lib/libsmb2.c report failure to the caller
as a bare -errno without calling smb2_set_nterror() first, so
smb2_get_error() afterwards returns stale text from some earlier operation.
The dart_smb2 wrapper surfaces smb2_get_error() to Dart exceptions, which
made these failures unreadable ("previous unrelated error" instead of e.g.
STATUS_OBJECT_NAME_NOT_FOUND).

Adds smb2_set_nterror() at the failure sites upstream missed:
  - the generic open/create callback ("Create failed with status ...")
  - smb2_stat_async CREATE failure and compound-status failure
  - smb2_truncate_async compound-status failure
"""
import sys
import os

root = sys.argv[1]
fn = os.path.join(root, "lib/libsmb2.c")
with open(fn) as f:
    content = f.read()

replacements = [
    # Generic open/create callback: use set_nterror so the NT status survives.
    (
        '                smb2_set_error(smb2, "Create failed with status %s.", '
        "nterror_to_str(status));\n",
        "                smb2_set_nterror(smb2, status,\n"
        '                                 "Create failed with status %s.",\n'
        "                                 nterror_to_str(status));\n",
    ),
    # smb2_stat_async: CREATE failed outright.
    (
        "        if (status != SMB2_STATUS_SUCCESS) {\n"
        "                stat_data->cb(smb2, -nterror_to_errno(status),\n"
        "                       NULL, stat_data->cb_data);\n"
        "                free(stat_data);\n"
        "                return;\n"
        "        }\n",
        "        if (status != SMB2_STATUS_SUCCESS) {\n"
        "                smb2_set_nterror(smb2, status, \"%s\",\n"
        "                                 nterror_to_str(status));\n"
        "                stat_data->cb(smb2, -nterror_to_errno(status),\n"
        "                       NULL, stat_data->cb_data);\n"
        "                free(stat_data);\n"
        "                return;\n"
        "        }\n",
    ),
    # smb2_stat_async: compound CLOSE callback with an accumulated status.
    (
        "        stat_data->cb(smb2, -nterror_to_errno(stat_data->status),\n",
        "        if (stat_data->status != SMB2_STATUS_SUCCESS) {\n"
        "                smb2_set_nterror(smb2, stat_data->status, \"%s\",\n"
        "                                 nterror_to_str(stat_data->status));\n"
        "        }\n"
        "\n"
        "        stat_data->cb(smb2, -nterror_to_errno(stat_data->status),\n",
    ),
    # smb2_truncate_async: compound CLOSE callback with an accumulated status.
    (
        "        trunc_data->cb(smb2, -nterror_to_errno(trunc_data->status),\n",
        "        if (trunc_data->status != SMB2_STATUS_SUCCESS) {\n"
        "                smb2_set_nterror(smb2, trunc_data->status, \"%s\",\n"
        "                                 nterror_to_str(trunc_data->status));\n"
        "        }\n"
        "\n"
        "        trunc_data->cb(smb2, -nterror_to_errno(trunc_data->status),\n",
    ),
]

for old, new in replacements:
    if old not in content:
        print("ERROR: anchor not found in lib/libsmb2.c (upstream drifted?):")
        print(old)
        sys.exit(1)
    content = content.replace(old, new, 1)

with open(fn, "w") as f:
    f.write(content)
print("Patched lib/libsmb2.c: NT status recorded on stat/truncate/create failures")
