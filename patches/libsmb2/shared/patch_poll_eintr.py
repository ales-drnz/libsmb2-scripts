# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Retry the sync-API poll() on EINTR.

wait_for_reply() in lib/sync.c fails the whole operation when poll() is
interrupted by a signal. Flutter apps get profiler / GC / debugger signals
routinely, and Dart FFI calls run the sync API on a helper isolate — an
EINTR there surfaced as a spurious "Poll failed" error mid-transfer.

Standard EINTR retry loop; every other poll() failure still errors out.
"""
import sys
import os

root = sys.argv[1]
fn = os.path.join(root, "lib/sync.c")
with open(fn) as f:
    content = f.read()

old = (
    "\t\tif (poll(&pfd, 1, 1000) < 0) {\n"
    '\t\t\tsmb2_set_error(smb2, "Poll failed");\n'
    "\t\t\treturn -1;\n"
    "\t\t}\n"
)
new = (
    "\t\t{\n"
    "\t\t\tint prc;\n"
    "\t\t\tdo {\n"
    "\t\t\t\tprc = poll(&pfd, 1, 1000);\n"
    "\t\t\t} while (prc < 0 && errno == EINTR);\n"
    "\t\t\tif (prc < 0) {\n"
    '\t\t\t\tsmb2_set_error(smb2, "Poll failed");\n'
    "\t\t\t\treturn -1;\n"
    "\t\t\t}\n"
    "\t\t}\n"
)

if old not in content:
    print("ERROR: poll() anchor not found in lib/sync.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/sync.c: poll() retries on EINTR")
