# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Make unlink fail on a directory.

smb2_unlink_async() opens the path with FILE_DELETE_ON_CLOSE and closes
it, without saying it wants a file. On a directory the server accepts the
open: an empty directory is deleted, and one that still has entries is
kept while the close succeeds ([MS-FSA] 2.1.5.4), so unlink() returned 0
and deleted nothing. dart_smb2's deleteFile() is unlink().

The open now also carries FILE_NON_DIRECTORY_FILE, so a directory fails
with STATUS_FILE_IS_A_DIRECTORY (-EPERM, which posix allows unlink() to
return for a directory), as DeleteFile does on Windows. This is the
mirror of patch_rmdir_disposition.py, whose FILE_DIRECTORY_FILE makes
rmdir on a file fail with STATUS_NOT_A_DIRECTORY. The symlink cleanup,
which removes a placeholder directory through the same function with
is_dir set, is left as it was.

Links to directories:
  - Windows: the open still carries FILE_OPEN_REPARSE_POINT, so it opens
    the link itself, and a directory junction or directory symlink is a
    directory object. unlink() of one now fails with
    STATUS_FILE_IS_A_DIRECTORY instead of removing the link; remove it
    with rmdir, which opens with FILE_DIRECTORY_FILE |
    FILE_OPEN_REPARSE_POINT and removes the link, not its target (as
    RemoveDirectory does on Windows). A symlink to a file is still
    removed by unlink().
  - Samba follows symlinks on the server and does not hand SMB2 the link
    itself without the SMB3 POSIX extensions, which libsmb2 does not
    negotiate. A symlink to a directory fails unlink() with
    STATUS_FILE_IS_A_DIRECTORY (it used to return 0 and stay) and rmdir()
    with STATUS_DIRECTORY_NOT_EMPTY or STATUS_NOT_A_DIRECTORY; it cannot
    be removed over SMB2, and its target is never touched. A symlink to a
    file is removed by unlink() and its target kept; a dangling symlink
    fails with STATUS_OBJECT_NAME_NOT_FOUND, as before.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

root = sys.argv[1]
fn = os.path.join(root, "lib/libsmb2.c")
with open(fn) as f:
    content = f.read()

old = (
    "        cr_req.create_options = SMB2_FILE_DELETE_ON_CLOSE |\n"
    "                SMB2_FILE_OPEN_REPARSE_POINT;\n"
    "        cr_req.name = path;\n"
    "\n"
    "        pdu = smb2_cmd_create_async(smb2, &cr_req, create_cb_1, create_data);\n"
)
new = (
    "        cr_req.create_options = SMB2_FILE_DELETE_ON_CLOSE |\n"
    "                SMB2_FILE_OPEN_REPARSE_POINT;\n"
    "        /* dart_smb2: unlink() of a directory fails with\n"
    "         * STATUS_FILE_IS_A_DIRECTORY (see patch_unlink_non_directory.py). */\n"
    "        if (!is_dir) {\n"
    "                cr_req.create_options |= SMB2_FILE_NON_DIRECTORY_FILE;\n"
    "        }\n"
    "        cr_req.name = path;\n"
    "\n"
    "        pdu = smb2_cmd_create_async(smb2, &cr_req, create_cb_1, create_data);\n"
)

if content.count(old) != 1:
    print("ERROR: smb2_unlink_internal create_options anchor not found exactly once in lib/libsmb2.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/libsmb2.c: unlink opens with FILE_NON_DIRECTORY_FILE")
