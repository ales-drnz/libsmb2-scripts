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

Those callbacks get command_data == NULL. Every compound callback in
lib/libsmb2.c checks the status before it reads the reply, except
fstat_cb_1 (the second PDU of smb2_fstat_async), which read
rep->output_buffer first: a NULL dereference that the timeout sweep of a
compound already sent could reach upstream, and this patch made reachable
for an unsent one and for smb2_destroy_context() too (an ASan build
crashes there; -O2 happened to move the load after the check). It now
reads the reply only after `status != SMB2_STATUS_SUCCESS || rep == NULL`,
as stat_attribute_tag_cb does (a NULL reply with a success status, which
nothing passes, becomes SMB2_STATUS_INTERNAL_ERROR).

patch_nterror_reporting.py edits the same lines: it puts smb2_set_nterror()
between the outqueue's SMB2_LIST_REMOVE and the head's callback, and in
fstat_cb_1's status check. The outqueue anchor is therefore found from one
line to the other rather than as one block, and fstat_cb_1's status check
is not touched, so the two patches apply in either order.

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

# lib/libsmb2.c: fstat_cb_1 reads the reply only once it knows it has one.
fn = os.path.join(root, "lib/libsmb2.c")
with open(fn) as f:
    content = f.read()

# The status check itself is left alone: patch_nterror_reporting.py anchors
# on it. A NULL reply with a success status, which no caller passes, is
# turned into an error before it.
old = (
    "        struct smb2_query_info_reply *rep = command_data;\n"
    "        struct smb2_file_all_info *fs = rep->output_buffer;\n"
    "        struct smb2_stat_64 *st = stat_data->st;\n"
    "\n"
)
new = (
    "        struct smb2_query_info_reply *rep = command_data;\n"
    "        struct smb2_file_all_info *fs;\n"
    "        struct smb2_stat_64 *st = stat_data->st;\n"
    "\n"
    "        /* dart_smb2: rep is NULL when an unsent compound times out or\n"
    "         * the context is destroyed (see patch_compound_callbacks.py):\n"
    "         * read it only after `status != SUCCESS || rep == NULL`. */\n"
    "        if (rep == NULL && status == SMB2_STATUS_SUCCESS) {\n"
    "                status = SMB2_STATUS_INTERNAL_ERROR;\n"
    "        }\n"
)
after_old = (
    "                free(stat_data);\n"
    "                return;\n"
    "        }\n"
    "\n"
    "        smb2_set_stat_type(st, fs->basic.file_attributes,\n"
)
after_new = (
    "                free(stat_data);\n"
    "                return;\n"
    "        }\n"
    "        fs = rep->output_buffer;\n"
    "\n"
    "        smb2_set_stat_type(st, fs->basic.file_attributes,\n"
)
if content.count(old) != 1 or content.count(after_old) != 1:
    print("ERROR: fstat_cb_1 anchor not found exactly once in lib/libsmb2.c (upstream drifted?)")
    sys.exit(1)
content = content.replace(old, new, 1).replace(after_old, after_new, 1)
with open(fn, "w") as f:
    f.write(content)

print("Patched lib/pdu.c, lib/init.c, lib/libsmb2.c: an unsent compound calls every PDU's callback on timeout and shutdown; fstat_cb_1 checks for a reply")
