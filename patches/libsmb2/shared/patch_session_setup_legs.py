# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Bound the legs of a session setup.

session_setup_cb() answers every STATUS_MORE_PROCESSING_REQUIRED with
another leg. Each leg is a request of its own with a timeout of its own,
so a server that answered every one that way kept smb2_connect_share()
going for ever, whatever smb2_set_timeout() said. NTLMSSP takes two legs
and Kerberos one or two; after sixteen the connect now fails.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402


p = Patch(sys.argv[1], sentinel=("lib/libsmb2.c", "session_legs"))

p.replace(
    "lib/libsmb2.c",
    "        void *auth_data;\n",
    "        void *auth_data;\n"
    "\n"
    "        /* dart_smb2: the legs of the session setup so far (see\n"
    "         * patch_session_setup_legs.py). */\n"
    "        int session_legs;\n",
)
p.replace(
    "lib/libsmb2.c",
    "        if (status == SMB2_STATUS_MORE_PROCESSING_REQUIRED &&\n"
    "            rep->security_buffer) {\n"
    "                smb3_update_preauth_hash(smb2, smb2->in.niov - 1, &smb2->in.iov[1]);\n",
    "        if (status == SMB2_STATUS_MORE_PROCESSING_REQUIRED &&\n"
    "            rep->security_buffer && ++c_data->session_legs > 16) {\n"
    "                smb2_close_context(smb2);\n"
    "                smb2_set_error(smb2, \"Session setup did not complete \"\n"
    "                               \"in %d legs\", c_data->session_legs - 1);\n"
    "                c_data->cb(smb2, -ECONNREFUSED, NULL, c_data->cb_data);\n"
    "                free_c_data(smb2, c_data);\n"
    "                return;\n"
    "        }\n"
    "        if (status == SMB2_STATUS_MORE_PROCESSING_REQUIRED &&\n"
    "            rep->security_buffer) {\n"
    "                smb3_update_preauth_hash(smb2, smb2->in.niov - 1, &smb2->in.iov[1]);\n",
)

p.done("Patched lib/libsmb2.c: a session setup ends after sixteen legs")
