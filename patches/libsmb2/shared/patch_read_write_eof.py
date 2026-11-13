# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Report 0 bytes at end of file without reading the reply.

read_cb() and write_cb() in lib/libsmb2.c let STATUS_END_OF_FILE through
as "no more data" and then hand the caller rep->data_length (read) or
rep->count (write). STATUS_END_OF_FILE has error severity, so the payload
of that reply is not a read or write reply: lib/pdu.c decodes it with
smb2_process_error_fixed() into a struct smb2_error_reply. Read through
the wrong type, data_length is the error reply's byte_count and count its
error_context_count, both taken off the wire: a server that puts error
data in its end-of-file reply made pread() return that many bytes it never
copied into the buffer.

Both callbacks now report 0 for STATUS_END_OF_FILE and leave the reply
alone.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

p = Patch(sys.argv[1], sentinel=("lib/libsmb2.c", "patch_read_write_eof.py"))

fixes = [
    # read_cb()
    (
        "        if (status == SMB2_STATUS_SUCCESS) {\n"
        "                rd->read_cb_data.fh->offset = rd->read_cb_data.offset + rep->data_length;\n"
        "        }\n",
        "        /* dart_smb2: at end of file the payload is an error reply, not a\n"
        "         * read reply (see patch_read_write_eof.py). */\n"
        "        if ((uint32_t)status == SMB2_STATUS_END_OF_FILE) {\n"
        "                rd->cb(smb2, 0, &rd->read_cb_data, rd->cb_data);\n"
        "                free(rd);\n"
        "                return;\n"
        "        }\n"
        "\n",
    ),
    # write_cb()
    (
        "        if (status == SMB2_STATUS_SUCCESS) {\n"
        "                wd->write_cb_data.fh->offset = wd->write_cb_data.offset + rep->count;\n"
        "        }\n",
        "        /* dart_smb2: at end of file the payload is an error reply, not a\n"
        "         * write reply (see patch_read_write_eof.py). */\n"
        "        if ((uint32_t)status == SMB2_STATUS_END_OF_FILE) {\n"
        "                wd->cb(smb2, 0, &wd->write_cb_data, wd->cb_data);\n"
        "                free(wd);\n"
        "                return;\n"
        "        }\n"
        "\n",
    ),
]

for old, prefix in fixes:
    p.replace("lib/libsmb2.c", old, prefix + old)

p.done("Patched lib/libsmb2.c: read and write report 0 at end of file without reading the reply")
