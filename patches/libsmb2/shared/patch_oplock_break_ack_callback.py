# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Give the acknowledgement of an oplock or lease break a callback.

smb2_oplock_break_notify() answers a break notification with an
acknowledgement it queues with a NULL callback. The server answers an
acknowledgement in turn (MS-SMB2 3.3.5.22), and smb2_read_data() calls the
callback of the PDU a reply belongs to without looking at it: the reply
made the client call address 0.

A client that never asked for an oplock or a lease, as dart_smb2, still
acknowledges a notification, so any server could stop the process with a
few notifications nobody asked for and the replies to their
acknowledgements. The jump is to address 0 and nowhere else: the process
stops, no memory is written.

The acknowledgements now have a callback that does nothing, and the reader
skips a callback that is not there.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402


p = Patch(sys.argv[1], sentinel=("lib/libsmb2.c", "oplock_break_ack_cb"))

# ── lib/libsmb2.c — a callback for the acknowledgements ──────────────────────
p.replace(
    "lib/libsmb2.c",
    "void\n"
    "smb2_oplock_break_notify(struct smb2_context *smb2, int status, void *command_data, void *cb_data)\n"
    "{\n",
    "/* dart_smb2: the server answers the acknowledgement of a break, and\n"
    " * nobody waits for that answer (see patch_oplock_break_ack_callback.py). */\n"
    "static void\n"
    "oplock_break_ack_cb(struct smb2_context *smb2 _U_, int status _U_,\n"
    "                    void *command_data _U_, void *cb_data _U_)\n"
    "{\n"
    "}\n"
    "\n"
    "void\n"
    "smb2_oplock_break_notify(struct smb2_context *smb2, int status, void *command_data, void *cb_data)\n"
    "{\n",
)
p.replace(
    "lib/libsmb2.c",
    "pdu = smb2_cmd_oplock_break_reply_async(smb2, &rep_oplock, NULL, cb_data);",
    "pdu = smb2_cmd_oplock_break_reply_async(smb2, &rep_oplock, oplock_break_ack_cb, cb_data);",
)
p.replace(
    "lib/libsmb2.c",
    "pdu = smb2_cmd_lease_break_reply_async(smb2, &rep_lease, NULL, cb_data);",
    "pdu = smb2_cmd_lease_break_reply_async(smb2, &rep_lease, oplock_break_ack_cb, cb_data);",
)

# ── lib/socket.c — a reply whose PDU has no callback ─────────────────────────
p.replace(
    "lib/socket.c",
    "        } else {\n"
    "                pdu->cb(smb2, smb2->hdr.status, pdu->payload, pdu->cb_data);\n"
    "                if (!pdu->caller_frees_pdu) {\n",
    "        } else {\n"
    "                if (pdu->cb) {\n"
    "                        pdu->cb(smb2, smb2->hdr.status, pdu->payload, pdu->cb_data);\n"
    "                }\n"
    "                if (!pdu->caller_frees_pdu) {\n",
)

p.done("Patched: the acknowledgement of an oplock break has a callback (libsmb2.c, socket.c)")
