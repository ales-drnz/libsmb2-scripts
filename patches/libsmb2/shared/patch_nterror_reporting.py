# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Record the NT status on every failure the caller may read it back for.

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
  - smb2_rename_async / smb2_link_async compound-status failure
  - smb2_echo_async failure
  - the timeout sweep (lib/pdu.c), which records SMB2_STATUS_IO_TIMEOUT
    before it calls a timed-out request's callback, so a timeout that no
    callback reports itself (echo, read, write, ...) no longer leaves the
    status of an earlier failure behind

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
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

replacements += [
    # smb2_rename_async / smb2_link_async: compound CLOSE callback.
    (
        "        new_name_data->cb(smb2, -nterror_to_errno(new_name_data->status),\n",
        "        if (new_name_data->status != SMB2_STATUS_SUCCESS) {\n"
        "                smb2_set_nterror(smb2, new_name_data->status, \"%s\",\n"
        "                                 nterror_to_str(new_name_data->status));\n"
        "        }\n"
        "\n"
        "        new_name_data->cb(smb2, -nterror_to_errno(new_name_data->status),\n",
    ),
    # smb2_echo_async.
    (
        "        struct smb2_echo_data *cb_data = private_data;\n"
        "\n"
        "        cb_data->cb(smb2, -nterror_to_errno(status),\n",
        "        struct smb2_echo_data *cb_data = private_data;\n"
        "\n"
        "        if (status != SMB2_STATUS_SUCCESS) {\n"
        "                smb2_set_nterror(smb2, status, \"%s\",\n"
        "                                 nterror_to_str(status));\n"
        "        }\n"
        "        cb_data->cb(smb2, -nterror_to_errno(status),\n",
    ),
]

for old, new in replacements:
    if content.count(old) != 1:
        print("ERROR: anchor not found exactly once in lib/libsmb2.c (upstream drifted?):")
        print(old)
        sys.exit(1)
    content = content.replace(old, new, 1)

with open(fn, "w") as f:
    f.write(content)

# lib/pdu.c: the timeout sweep, outqueue and waitqueue.
fn = os.path.join(root, "lib/pdu.c")
with open(fn) as f:
    content = f.read()

old = (
    "                        pdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT, NULL,\n"
    "                                pdu->cb_data);\n"
)
new = (
    "                        smb2_set_nterror(smb2, SMB2_STATUS_IO_TIMEOUT, \"%s\",\n"
    "                                         nterror_to_str(SMB2_STATUS_IO_TIMEOUT));\n"
    + old
)
if content.count(old) != 2:
    print("ERROR: the two timeout callbacks of smb2_timeout_pdus() not found in lib/pdu.c (upstream drifted?)")
    sys.exit(1)
content = content.replace(old, new)

with open(fn, "w") as f:
    f.write(content)
print("Patched lib/libsmb2.c, lib/pdu.c: NT status recorded on create/stat/truncate/rename/echo failures and timeouts")
