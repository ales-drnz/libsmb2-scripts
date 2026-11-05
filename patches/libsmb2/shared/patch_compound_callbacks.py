# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Call every callback of a compound that times out before it is sent.

rmdir, unlink, mkdir, stat, truncate, rename and the other path calls
queue a compound (CREATE + ... + CLOSE) whose first callbacks only record
the status: the last one, the CLOSE's, calls the caller and frees the call
data. Once the compound is on the wire every PDU waits for its own reply,
and the timeout sweep calls each one, so that works.

A compound still in the outqueue (no credits yet, or the socket not
writable) is one list entry, though. smb2_timeout_pdus() calls the head's
callback only, and smb2_free_pdu() frees the rest of the chain without
calling theirs: the caller was never told, the call data leaked, and the
synchronous smb2_rmdir() / smb2_unlink() kept polling in wait_for_reply()
after the timeout had expired.

The sweep now calls the callback of every PDU in the chain, head first,
with SMB2_STATUS_IO_TIMEOUT, as the reply and timeout paths do for a
compound already sent: the caller gets one callback with -ETIMEDOUT and the
data is freed. Upstream does the same for smb2_destroy_context() since
ee56559 / b4a409e, and its compound callbacks (fstat_cb_1 included) read
the reply only after checking the status, so a NULL reply is safe.

patch_nterror_reporting.py puts smb2_set_nterror() between the outqueue's
SMB2_LIST_REMOVE and the head's callback, so the anchor is found from one
line to the other rather than as one block, and the two patches apply in
either order.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

root = sys.argv[1]

# lib/pdu.c: the timeout sweep of the outqueue.
fn = os.path.join(root, "lib/pdu.c")
with open(fn) as f:
    content = f.read()

# Anchored from the outqueue's SMB2_LIST_REMOVE to the head's callback
# rather than on the two lines together: patch_nterror_reporting.py puts
# smb2_set_nterror() between them, and either may run first.
remove = "                        SMB2_LIST_REMOVE(&smb2->outqueue, pdu);\n"
head_cb = (
    "                        pdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT, NULL,\n"
    "                                pdu->cb_data);\n"
)
loop = (
    "                        /* dart_smb2: an unsent compound is one entry;\n"
    "                         * its other PDUs get their callbacks too (see\n"
    "                         * patch_compound_callbacks.py). */\n"
    "                        {\n"
    "                                struct smb2_pdu *cpdu;\n"
    "\n"
    "                                for (cpdu = pdu->next_compound; cpdu;\n"
    "                                     cpdu = cpdu->next_compound) {\n"
    "                                        if (cpdu->cb) {\n"
    "                                                cpdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT,\n"
    "                                                         NULL, cpdu->cb_data);\n"
    "                                        }\n"
    "                                }\n"
    "                        }\n"
)
if content.count(remove) != 1 or content.count(head_cb) != 2:
    print("ERROR: outqueue timeout anchor not found in lib/pdu.c (upstream drifted?)")
    sys.exit(1)
at = content.index(head_cb, content.index(remove))
if "SMB2_LIST_REMOVE(&smb2->waitqueue" in content[content.index(remove):at]:
    print("ERROR: outqueue timeout callback not found in lib/pdu.c (upstream drifted?)")
    sys.exit(1)
at += len(head_cb)
with open(fn, "w") as f:
    f.write(content[:at] + loop + content[at:])

print("Patched lib/pdu.c: an unsent compound calls every PDU's callback on timeout")
