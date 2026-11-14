# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Do not sign the TREE_CONNECT of a guest or null session on SMB 3.1.1.

On SMB 3.1.1 the client signs its TREE_CONNECT so that the server can
check the preauth integrity hash. A guest or null session has no key to
do that with (MS-SMB2 3.2.4.1.1 signs for a session that is neither), and
libsmb2 signed all the same: a server that maps an unknown user to guest
answered STATUS_ACCESS_DENIED to the TREE_CONNECT of a share that allows
guests, where the same logon works up to SMB 3.0.2 and with smbclient.
libsmb2 as a server already makes this exception for its replies.

The context now keeps whether the server said the session is guest or
null, and the TREE_CONNECT of such a session goes unsigned unless signing
was asked for. The flag comes from an unsigned reply: one forged on a
session that is not guest only makes the server refuse the unsigned
TREE_CONNECT.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402


p = Patch(sys.argv[1], sentinel=("include/libsmb2-private.h", "session_is_guest"))

p.replace(
    "include/libsmb2-private.h",
    "        const struct addrinfo *next_addrinfo;\n",
    "        const struct addrinfo *next_addrinfo;\n"
    "\n"
    "        /* dart_smb2: the server said the session is guest or null (see\n"
    "         * patch_guest_tree_connect.py). */\n"
    "        int session_is_guest;\n",
)
p.replace(
    "lib/libsmb2.c",
    "        if (smb2->seal_requested != SMB2_SEAL_NONE &&\n"
    "            (rep->session_flags & SMB2_SESSION_FLAG_IS_ENCRYPT_DATA)) {\n",
    "        smb2->session_is_guest =\n"
    "                (rep->session_flags & (SMB2_SESSION_FLAG_IS_GUEST |\n"
    "                                       SMB2_SESSION_FLAG_IS_NULL)) != 0;\n"
    "\n"
    "        if (smb2->seal_requested != SMB2_SEAL_NONE &&\n"
    "            (rep->session_flags & SMB2_SESSION_FLAG_IS_ENCRYPT_DATA)) {\n",
)
p.replace(
    "lib/libsmb2.c",
    "        smb2->message_id = 0;\n"
    "        smb2->session_id = 0;\n"
    "        smb2->enc_keys_ready = 0;\n",
    "        smb2->message_id = 0;\n"
    "        smb2->session_id = 0;\n"
    "        smb2->session_is_guest = 0;\n"
    "        smb2->enc_keys_ready = 0;\n",
)
p.replace(
    "lib/pdu.c",
    "(p->header.command == SMB2_TREE_CONNECT && smb2->dialect == SMB2_VERSION_0311 && !smb2->seal))) {",
    "(p->header.command == SMB2_TREE_CONNECT && smb2->dialect == SMB2_VERSION_0311 && !smb2->seal &&\n"
    "                     !smb2->session_is_guest))) {",
)

p.done("Patched: the TREE_CONNECT of a guest session is not signed on SMB 3.1.1 (libsmb2-private.h, libsmb2.c, pdu.c)")
