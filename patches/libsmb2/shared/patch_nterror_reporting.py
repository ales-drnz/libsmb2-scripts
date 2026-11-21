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

Upstream sets it in the stat, fstat, truncate, rename and echo callbacks
since 8fa34fd, and in the generic open/create callback (create_cb_1) since
de3c632 (libsmb2 7.0.0). This adds it where it is still missing: the
timeout sweep (lib/pdu.c) now records SMB2_STATUS_IO_TIMEOUT before it
calls a timed-out request's callback, so a timeout that no callback
reports itself (echo, read, write, ...) no longer leaves the status of an
earlier failure behind.

patch_reply_stall_timeout.py adds a third branch after the two queues and
records the status itself; the two patches apply in either order.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

p = Patch(
    sys.argv[1],
    sentinel=("lib/pdu.c", 'smb2_set_nterror(smb2, SMB2_STATUS_IO_TIMEOUT, "%s",'),
)

record = (
    "                        smb2_set_nterror(smb2, SMB2_STATUS_IO_TIMEOUT, \"%s\",\n"
    "                                         nterror_to_str(SMB2_STATUS_IO_TIMEOUT));\n"
)

# lib/pdu.c: the timeout sweep. The outqueue branch fires every pdu of an
# unsent compound, the waitqueue branch one pdu.
old = (
    "                         * siblings' references.\n"
    "                         */\n"
    "                        for (p = pdu; p; p = p->next_compound) {\n"
)
p.replace("lib/pdu.c", old, old.replace(
    "                        for (p = pdu;", record + "                        for (p = pdu;"))

old = (
    "                        SMB2_LIST_REMOVE(&smb2->waitqueue, pdu);\n"
    "                        if (pdu->cb) {\n"
)
p.replace("lib/pdu.c", old, old.replace(
    "                        if (pdu->cb) {", record + "                        if (pdu->cb) {"))

p.done("Patched lib/pdu.c: NT status recorded on timeouts")
