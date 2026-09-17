# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Free the sync smb2_open() callback data.

smb2_open() in lib/sync.c hands its sync_cb_data to smb2_open_async_pdu()
with free_cb=free, expecting the pdu to free it. But
_smb2_open_async_with_oplock_or_lease() in lib/libsmb2.c never stores
free_cb — and it could not: that pdu's cb_data is the smb2fh, not the sync
data. So every synchronous open leaked its sync_cb_data (16 bytes on
64-bit), successful or not.

smb2_open() owns cb_data for the whole call (no callback can reach it once
the pdu is freed, which also unlinks it from the queues), so it frees it
itself on both return paths and passes free_cb=NULL.
"""
import sys
import os

root = sys.argv[1]
fn = os.path.join(root, "lib/sync.c")
with open(fn) as f:
    content = f.read()

old = (
    "        /* pdu takes ownership of cb_data and will free it when the pdu is freed */\n"
    "\tpdu = smb2_open_async_pdu(smb2, path, flags, sync_open_cb, cb_data, free);\n"
    "        if (pdu == NULL) {\n"
    '\t\tsmb2_set_error(smb2, "smb2_open_async failed");\n'
    "                free(cb_data);\n"
    "\t\treturn NULL;\n"
    "\t}\n"
    "\n"
    "\tif (wait_for_reply(smb2, cb_data) < 0) {\n"
    "                smb2_free_pdu(smb2, pdu);\n"
    "                return NULL;\n"
    "        }\n"
    "\n"
    "\tptr = cb_data->ptr;\n"
    "        cb_data->ptr = NULL;\n"
    "        smb2_free_pdu(smb2, pdu);\n"
    "        return ptr;\n"
)
new = (
    "        /* smb2_open_async_pdu() never stores free_cb, so cb_data stays ours */\n"
    "\tpdu = smb2_open_async_pdu(smb2, path, flags, sync_open_cb, cb_data, NULL);\n"
    "        if (pdu == NULL) {\n"
    '\t\tsmb2_set_error(smb2, "smb2_open_async failed");\n'
    "                free(cb_data);\n"
    "\t\treturn NULL;\n"
    "\t}\n"
    "\n"
    "\tif (wait_for_reply(smb2, cb_data) < 0) {\n"
    "                smb2_free_pdu(smb2, pdu);\n"
    "                free(cb_data);\n"
    "                return NULL;\n"
    "        }\n"
    "\n"
    "\tptr = cb_data->ptr;\n"
    "        smb2_free_pdu(smb2, pdu);\n"
    "        free(cb_data);\n"
    "        return ptr;\n"
)

if old not in content:
    print("ERROR: smb2_open() anchor not found in lib/sync.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/sync.c: smb2_open() frees its sync callback data")
