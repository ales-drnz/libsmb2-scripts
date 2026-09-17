# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Do not free caller-owned pdus when they time out.

Since upstream 3818a74a ("open/opendir: Start converting to _async_pdu()
api") the sync smb2_open() / smb2_opendir() build their pdu with
caller_frees_pdu=1 and free it themselves after wait_for_reply().
smb2_timeout_pdus() in lib/pdu.c ignored that flag: it ran the callback
(which marks the sync call finished) and freed the pdu, so wait_for_reply()
returned 0 and the sync caller freed the same pdu again — a double free that
aborts the process (SIGABRT under Android's Scudo) whenever an open or a
directory listing times out against an unresponsive server.

The reply path in lib/socket.c already honours caller_frees_pdu; apply the
same guard to both timeout loops (outqueue and waitqueue). The pdu is still
unlinked from its queue, so the caller's later smb2_free_pdu() is safe.

Upstream: https://github.com/sahlberg/libsmb2/issues/484
"""
import sys
import os

root = sys.argv[1]
fn = os.path.join(root, "lib/pdu.c")
with open(fn) as f:
    content = f.read()

old = (
    "                        pdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT, NULL,\n"
    "                                pdu->cb_data);\n"
    "                        smb2_free_pdu(smb2, pdu);\n"
)
new = (
    "                        pdu->cb(smb2, SMB2_STATUS_IO_TIMEOUT, NULL,\n"
    "                                pdu->cb_data);\n"
    "                        if (!pdu->caller_frees_pdu) {\n"
    "                                smb2_free_pdu(smb2, pdu);\n"
    "                        }\n"
)

count = content.count(old)
if count != 2:
    print(f"ERROR: expected 2 timeout free sites in lib/pdu.c, found {count} (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new))
print("Patched lib/pdu.c: timed-out pdus honour caller_frees_pdu")
