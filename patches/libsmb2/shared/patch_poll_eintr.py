# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Retry the sync-API poll() on EINTR.

wait_for_reply() in lib/sync.c fails the whole operation when poll() is
interrupted by a signal. Flutter apps get profiler / GC / debugger signals
routinely, and Dart FFI calls run the sync API on a helper isolate — an
EINTR there surfaced as a spurious "Poll failed" error mid-transfer.

Standard EINTR retry loop; every other poll() failure still errors out.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

p = Patch(sys.argv[1], sentinel=("lib/sync.c", 'prc = poll(&pfd, 1, 1000);'))

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
p.replace("lib/sync.c", old, new)
p.done("Patched lib/sync.c: poll() retries on EINTR")
