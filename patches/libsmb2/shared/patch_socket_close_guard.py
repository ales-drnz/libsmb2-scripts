# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Stop the read loop when a PDU callback closed the context.

smb2_read_data() loops reading from smb2->fd. A callback fired while a PDU
is being processed may tear the connection down — e.g. the TREE_CONNECT
failure path closes the socket. The loop then keeps reading from a fd that
is no longer valid and reports a bogus low-level socket error, masking the
real one that was already set on the context.

Bail out of the loop (successfully — the real error is already recorded)
when the socket is gone after PDU processing.
"""
import sys
import os

root = sys.argv[1]
fn = os.path.join(root, "lib/socket.c")
with open(fn) as f:
    content = f.read()

old = (
    "                if (count) {\n"
    "                        return count;\n"
    "                }\n"
    "        }\n"
    "}\n"
)
new = (
    "                if (count) {\n"
    "                        return count;\n"
    "                }\n"
    "                /* A callback fired during PDU processing may have closed the\n"
    "                 * context (e.g. on a TREE_CONNECT failure).  If so, stop\n"
    "                 * trying to read — the real error is already set. */\n"
    "                if (!SMB2_VALID_SOCKET(smb2->fd)) {\n"
    "                        return 0;\n"
    "                }\n"
    "        }\n"
    "}\n"
)

if old not in content:
    print("ERROR: read-loop anchor not found in lib/socket.c (upstream drifted?)")
    sys.exit(1)
if content.count(old) != 1:
    print("ERROR: read-loop anchor is not unique in lib/socket.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/socket.c: read loop stops when a callback closed the context")
