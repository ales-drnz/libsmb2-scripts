# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Call every callback of a compound that is dropped before it is sent.

rmdir, unlink, mkdir, stat, truncate, rename and the other path calls
queue a compound (CREATE + ... + CLOSE) whose first callbacks only record
the status: the last one, the CLOSE's, calls the caller and frees the call
data. Once the compound is on the wire every PDU waits for its own reply,
and the timeout sweep calls each one, so that works.

A compound still in the outqueue (no credits yet, or the socket not
writable) is one list entry, though. smb2_timeout_pdus() and
smb2_destroy_context() call the head's callback only, and smb2_free_pdu()
frees the rest of the chain without calling theirs: the caller was never
told, the call data leaked, and the synchronous smb2_rmdir() / smb2_unlink()
kept polling in wait_for_reply() after the timeout had expired.

Both now call the callback of every PDU in the chain, head first, with the
same status (SMB2_STATUS_IO_TIMEOUT or SMB2_STATUS_SHUTDOWN), as the reply
and timeout paths do for a compound already sent: the caller gets one
callback with -ETIMEDOUT (or the shutdown status) and the data is freed.

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

old = (
    "                        SMB2_LIST_REMOVE(&smb2->outqueue, pdu);\n"
    "                        pdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT, NULL,\n"
    "                                pdu->cb_data);\n"
)
new = old + (
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
if content.count(old) != 1:
    print("ERROR: outqueue timeout anchor not found exactly once in lib/pdu.c (upstream drifted?)")
    sys.exit(1)
with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))

# lib/init.c: smb2_destroy_context() draining the outqueue.
fn = os.path.join(root, "lib/init.c")
with open(fn) as f:
    content = f.read()

old = (
    "                smb2->outqueue = pdu->next;\n"
    "                if (pdu->cb) {\n"
    "                        pdu->cb(smb2, SMB2_STATUS_SHUTDOWN, NULL, pdu->cb_data);\n"
    "                }\n"
)
new = old + (
    "                /* dart_smb2: see patch_compound_callbacks.py. */\n"
    "                {\n"
    "                        struct smb2_pdu *cpdu;\n"
    "\n"
    "                        for (cpdu = pdu->next_compound; cpdu;\n"
    "                             cpdu = cpdu->next_compound) {\n"
    "                                if (cpdu->cb) {\n"
    "                                        cpdu->cb(smb2, SMB2_STATUS_SHUTDOWN,\n"
    "                                                 NULL, cpdu->cb_data);\n"
    "                                }\n"
    "                        }\n"
    "                }\n"
)
if content.count(old) != 1:
    print("ERROR: destroy outqueue anchor not found exactly once in lib/init.c (upstream drifted?)")
    sys.exit(1)
with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))

print("Patched lib/pdu.c, lib/init.c: an unsent compound calls every PDU's callback on timeout and shutdown")
