# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Complete what is queued when the wait of a sync call fails.

A sync call that gave up waiting (smb2_service() failed on a reply it
could not parse, poll() failed, the connection never came) left its PDU
queued and returned. The PDU's callback still pointed at the file handle,
whose own callback and data the next call on that handle replaced; and a
PDU whose reply had started to arrive stayed in smb2->pdu, where nothing
completed it. smb2_destroy_context() then completed every PDU it found
with SMB2_STATUS_SHUTDOWN, and those callbacks read the data of calls
that had returned and freed it long before: a use after free on
smb2_destroy_context(), after a fsync, a stat or a close whose reply was
malformed and a later call on the same handle.

wait_for_reply() now completes every queued PDU with SMB2_STATUS_SHUTDOWN
before it reports the failure, while the data their callbacks reach is
that of the call that is failing. The error the caller reads stays the one
of the failure. A call whose callback has run this way frees its own data
in place of leaving it to a callback that will not come again, as
smb2_close() already did. stat, fstat and statvfs do the same upstream
since c94a9e1 and are left as they are.

A call on a context whose connection is gone (closed by a failure, or by
patch_reply_stall_timeout.py) waited for its whole timeout before it said
so. It now fails at once with "Not connected to a server"; a connect,
whose socket is not there yet, waits as before.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402


p = Patch(sys.argv[1], sentinel=("lib/sync.c", "sync_abort_pdus"))

# ── wait_for_reply() becomes the wait and what follows a failed one ──────────
p.replace(
    "lib/sync.c",
    "static int wait_for_reply(struct smb2_context *smb2,\n"
    "                          struct sync_cb_data *cb_data)\n"
    "{\n"
    "        time_t t = time(NULL);\n",
    "/* dart_smb2: complete every queued PDU with SMB2_STATUS_SHUTDOWN, as\n"
    " * smb2_destroy_context() does, and keep the error of the failure that\n"
    " * led here (see patch_wait_abort.py). A PDU its caller frees is left to\n"
    " * it. */\n"
    "static void sync_abort_pdus(struct smb2_context *smb2)\n"
    "{\n"
    "        char *error = strdup(smb2_get_error(smb2));\n"
    "        int nterror = smb2->nterror;\n"
    "\n"
    "        while (smb2->outqueue || smb2->pdu || smb2->next_pdu ||\n"
    "               smb2->waitqueue) {\n"
    "                while (smb2->outqueue) {\n"
    "                        struct smb2_pdu *pdu = smb2->outqueue;\n"
    "                        struct smb2_pdu *p;\n"
    "\n"
    "                        smb2->outqueue = pdu->next;\n"
    "                        for (p = pdu; p; p = p->next_compound) {\n"
    "                                if (p->cb) {\n"
    "                                        p->cb(smb2, SMB2_STATUS_SHUTDOWN,\n"
    "                                              NULL, p->cb_data);\n"
    "                                }\n"
    "                        }\n"
    "                        if (!pdu->caller_frees_pdu) {\n"
    "                                smb2_free_pdu(smb2, pdu);\n"
    "                        }\n"
    "                }\n"
    "                if (smb2->pdu) {\n"
    "                        struct smb2_pdu *pdu = smb2->pdu;\n"
    "\n"
    "                        smb2->pdu = NULL;\n"
    "                        if (pdu_on_list(smb2->waitqueue, pdu)) {\n"
    "                                continue;\n"
    "                        }\n"
    "                        if (pdu->cb) {\n"
    "                                pdu->cb(smb2, SMB2_STATUS_SHUTDOWN, NULL,\n"
    "                                        pdu->cb_data);\n"
    "                        }\n"
    "                        if (!pdu->caller_frees_pdu) {\n"
    "                                smb2_free_pdu(smb2, pdu);\n"
    "                        }\n"
    "                }\n"
    "                if (smb2->next_pdu) {\n"
    "                        struct smb2_pdu *pdu = smb2->next_pdu;\n"
    "\n"
    "                        smb2->next_pdu = NULL;\n"
    "                        if (pdu_on_list(smb2->waitqueue, pdu)) {\n"
    "                                continue;\n"
    "                        }\n"
    "                        if (pdu->cb) {\n"
    "                                pdu->cb(smb2, SMB2_STATUS_SHUTDOWN, NULL,\n"
    "                                        pdu->cb_data);\n"
    "                        }\n"
    "                        if (!pdu->caller_frees_pdu) {\n"
    "                                smb2_free_pdu(smb2, pdu);\n"
    "                        }\n"
    "                }\n"
    "                while (smb2->waitqueue) {\n"
    "                        struct smb2_pdu *pdu = smb2->waitqueue;\n"
    "\n"
    "                        smb2->waitqueue = pdu->next;\n"
    "                        if (pdu->cb) {\n"
    "                                pdu->cb(smb2, SMB2_STATUS_SHUTDOWN, NULL,\n"
    "                                        pdu->cb_data);\n"
    "                        }\n"
    "                        if (!pdu->caller_frees_pdu) {\n"
    "                                smb2_free_pdu(smb2, pdu);\n"
    "                        }\n"
    "                }\n"
    "        }\n"
    "        smb2_free_iovector(smb2, &smb2->in);\n"
    "        smb2->in.num_done = 0;\n"
    "        if (error) {\n"
    "                smb2_set_error(smb2, \"%s\", error);\n"
    "                free(error);\n"
    "        }\n"
    "        smb2->nterror = nterror;\n"
    "}\n"
    "\n"
    "static int wait_for_reply_inner(struct smb2_context *smb2,\n"
    "                                struct sync_cb_data *cb_data);\n"
    "\n"
    "/* dart_smb2: the wait of a sync call. A call on a connection that is\n"
    " * gone fails at once, and a wait that fails completes what is queued\n"
    " * (see patch_wait_abort.py). */\n"
    "static int wait_for_reply(struct smb2_context *smb2,\n"
    "                          struct sync_cb_data *cb_data)\n"
    "{\n"
    "        int rc;\n"
    "\n"
    "        if (!SMB2_VALID_SOCKET(smb2->fd) &&\n"
    "            smb2->connecting_fds_count == 0 &&\n"
    "            cb_data != &smb2->connect_cb_data) {\n"
    "                smb2_set_error(smb2, \"Not connected to a server\");\n"
    "                sync_abort_pdus(smb2);\n"
    "                return -1;\n"
    "        }\n"
    "        rc = wait_for_reply_inner(smb2, cb_data);\n"
    "        if (rc < 0) {\n"
    "                sync_abort_pdus(smb2);\n"
    "        }\n"
    "        return rc;\n"
    "}\n"
    "\n"
    "static int wait_for_reply_inner(struct smb2_context *smb2,\n"
    "                                struct sync_cb_data *cb_data)\n"
    "{\n"
    "        time_t t = time(NULL);\n",
)

# ── the calls that left their data to the callback ───────────────────────────
# A call whose callback has run frees its data at `out`, as smb2_close().
p.replace(
    "lib/sync.c",
    "        if (rc < 0) {\n"
    "                cb_data->status = SMB2_STATUS_CANCELLED;\n"
    "                return rc;\n",
    "        if (rc < 0) {\n"
    "                if (cb_data->is_finished) {\n"
    "                        goto out;\n"
    "                }\n"
    "                cb_data->status = SMB2_STATUS_CANCELLED;\n"
    "                return rc;\n",
    count=17,
)
p.replace(
    "lib/sync.c",
    "                cb_data->status = SMB2_STATUS_CANCELLED;\n"
    "                return NULL;\n",
    "                if (cb_data->is_finished) {\n"
    "                        free(cb_data);\n"
    "                        return NULL;\n"
    "                }\n"
    "                cb_data->status = SMB2_STATUS_CANCELLED;\n"
    "                return NULL;\n",
    count=2,
)

p.done("Patched: a failed wait completes what is queued (sync.c)")
