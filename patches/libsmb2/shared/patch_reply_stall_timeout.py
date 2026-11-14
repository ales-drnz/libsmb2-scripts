# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Time out a reply that stops arriving.

smb2_timeout_pdus() looks at the PDUs still to send and at those waiting
for a reply. A PDU whose reply has started to arrive is in neither queue:
smb2_read_data() takes it off the wait queue when the header matches and
keeps it in smb2->pdu until the body is complete. A server that sends a
header, or a session packet length larger than what follows, and then
nothing, left the call waiting for ever whatever smb2_set_timeout() said.

The context now records when it last received bytes. A reply in progress
that got none for the timeout fails with STATUS_IO_TIMEOUT like a reply
that never came, and the connection is closed: the rest of that reply may
still arrive, and the stream cannot be read from the middle of it. A large
reply that keeps arriving is not cut, however long it takes.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402


p = Patch(sys.argv[1], sentinel=("include/libsmb2-private.h", "last_read"))

p.replace(
    "include/libsmb2-private.h",
    "        int timeout;\n",
    "        int timeout;\n"
    "        /* dart_smb2: when bytes were last received, for the timeout of a\n"
    "         * reply in progress (see patch_reply_stall_timeout.py). */\n"
    "        time_t last_read;\n",
)

# ── lib/socket.c — every successful read counts as progress ──────────────────
p.replace(
    "lib/socket.c",
    "        if (count == 0) {\n"
    "                /* remote side has closed the socket. */\n",
    "        if (count > 0) {\n"
    "                smb2->last_read = time(NULL);\n"
    "        }\n"
    "        if (count == 0) {\n"
    "                /* remote side has closed the socket. */\n",
)

# ── lib/pdu.c — the reply in progress times out too ──────────────────────────
p.replace(
    "lib/pdu.c",
    "                pdu = next;\n"
    "        }\n"
    "}\n",
    "                pdu = next;\n"
    "        }\n"
    "\n"
    "        /* dart_smb2: the PDU whose reply is being received is in neither\n"
    "         * queue. When the reply stopped arriving, fail it, and close the\n"
    "         * connection: the stream cannot be read from the middle of a\n"
    "         * reply (see patch_reply_stall_timeout.py). */\n"
    "        pdu = smb2->pdu;\n"
    "        if (!smb2_is_server(smb2) && pdu && pdu->timeout &&\n"
    "            pdu->timeout < t && smb2->last_read + smb2->timeout < t) {\n"
    "                smb2->pdu = NULL;\n"
    "                smb2_close_context(smb2);\n"
    "                smb2_free_iovector(smb2, &smb2->in);\n"
    "                smb2->in.num_done = 0;\n"
    "                smb2_set_nterror(smb2, SMB2_STATUS_IO_TIMEOUT,\n"
    "                                 \"%s\", nterror_to_str(SMB2_STATUS_IO_TIMEOUT));\n"
    "                if (pdu->cb) {\n"
    "                        pdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT,\n"
    "                                NULL, pdu->cb_data);\n"
    "                }\n"
    "                if (!pdu->caller_frees_pdu) {\n"
    "                        smb2_free_pdu(smb2, pdu);\n"
    "                }\n"
    "        }\n"
    "}\n",
)

p.done("Patched: a reply that stops arriving times out (libsmb2-private.h, socket.c, pdu.c)")
