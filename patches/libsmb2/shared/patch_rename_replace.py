# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Add smb2_rename2 / smb2_rename2_async — rename that may replace the target.

smb2_rename_async() sends FileRenameInformation with ReplaceIfExists set to
0, so a rename onto an existing file always fails with
STATUS_OBJECT_NAME_COLLISION, and a caller that wants POSIX rename()
semantics has to delete the target first, which leaves a window with no
file at all. dart_smb2 exposes `rename(..., overwrite: true)` on top of
this API.

smb2_rename2() takes flags; SMB2_RENAME_REPLACE_IF_EXISTS sets
ReplaceIfExists, so the server replaces an existing file in one step. A
directory, or a file another handle holds open, is still not replaced: the
server answers STATUS_ACCESS_DENIED or STATUS_SHARING_VIOLATION.
smb2_rename() and smb2_link() keep sending 0.

Touches:
  include/smb2/libsmb2.h  — SMB2_RENAME_REPLACE_IF_EXISTS, declarations
  lib/libsmb2.c           — replace_if_exist through smb2_new_name_async
  lib/sync.c              — smb2_rename2 sync wrapper
  lib/libsmb2.syms        — export list entries

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

root = sys.argv[1]

# Every edit is applied to an in-memory copy first and the files are written
# only once all of them matched, so a drifted anchor leaves the tree as it
# was instead of half-patched.
files = {}


def patch(relpath, old, new):
    if relpath not in files:
        with open(os.path.join(root, relpath)) as f:
            files[relpath] = f.read()
    content = files[relpath]
    if content.count(old) != 1:
        print(f"ERROR: anchor not found exactly once in {relpath} (upstream drifted?)")
        sys.exit(1)
    files[relpath] = content.replace(old, new, 1)


# Already applied (a second run on the same tree): nothing to do.
with open(os.path.join(root, "include/smb2/libsmb2.h")) as f:
    if "SMB2_RENAME_REPLACE_IF_EXISTS" in f.read():
        print("Already patched: smb2_rename2 / smb2_rename2_async")
        sys.exit(0)


# ── include/smb2/libsmb2.h — public declarations ─────────────────────────────
patch(
    "include/smb2/libsmb2.h",
    "int smb2_rename(struct smb2_context *smb2, const char *oldpath,\n"
    "                const char *newpath);\n",
    "int smb2_rename(struct smb2_context *smb2, const char *oldpath,\n"
    "                const char *newpath);\n"
    "\n"
    "/*\n"
    " * Flags for smb2_rename2()\n"
    " */\n"
    "/*\n"
    " * Replace newpath when it exists (FileRenameInformation's\n"
    " * ReplaceIfExists). The server still refuses to replace a directory or\n"
    " * a file that is open elsewhere.\n"
    " */\n"
    "#define SMB2_RENAME_REPLACE_IF_EXISTS 0x00000001\n"
    "\n"
    "/*\n"
    " * Async rename2(): smb2_rename_async() with flags.\n"
    " *\n"
    " * Returns\n"
    " *  0     : The operation was initiated. Result of the operation will be\n"
    " *          reported through the callback function.\n"
    " * -errno : There was an error. The callback function will not be invoked.\n"
    " *\n"
    " * When the callback is invoked, status indicates the result:\n"
    " *      0 : Success.\n"
    " * -errno : An error occurred.\n"
    " */\n"
    "int smb2_rename2_async(struct smb2_context *smb2, const char *oldpath,\n"
    "                       const char *newpath, uint32_t flags,\n"
    "                       smb2_command_cb cb, void *cb_data);\n"
    "\n"
    "/*\n"
    " * Sync rename2()\n"
    " */\n"
    "int smb2_rename2(struct smb2_context *smb2, const char *oldpath,\n"
    "                 const char *newpath, uint32_t flags);\n",
)

# ── lib/libsmb2.c — replace_if_exist through smb2_new_name_async ─────────────
patch(
    "lib/libsmb2.c",
    "                    const char *newpath, uint8_t file_info_class,\n"
    "                    uint32_t desired_access,\n"
    "                    smb2_command_cb cb, void *cb_data)\n",
    "                    const char *newpath, uint8_t file_info_class,\n"
    "                    uint32_t desired_access, uint8_t replace_if_exist,\n"
    "                    smb2_command_cb cb, void *cb_data)\n",
)
patch(
    "lib/libsmb2.c",
    "                ln_info.replace_if_exist = 0;\n",
    "                ln_info.replace_if_exist = replace_if_exist;\n",
)
patch(
    "lib/libsmb2.c",
    "                rn_info.replace_if_exist = 0;\n",
    "                rn_info.replace_if_exist = replace_if_exist;\n",
)
patch(
    "lib/libsmb2.c",
    "int\n"
    "smb2_rename_async(struct smb2_context *smb2, const char *oldpath,\n"
    "                  const char *newpath, smb2_command_cb cb, void *cb_data)\n"
    "{\n"
    "        return smb2_new_name_async(smb2, oldpath, newpath,\n"
    "                                   SMB2_FILE_RENAME_INFORMATION,\n"
    "                                   SMB2_GENERIC_READ |\n"
    "                                   SMB2_FILE_READ_ATTRIBUTES |\n"
    "                                   SMB2_DELETE,\n"
    "                                   cb, cb_data);\n"
    "}\n",
    "int\n"
    "smb2_rename2_async(struct smb2_context *smb2, const char *oldpath,\n"
    "                   const char *newpath, uint32_t flags,\n"
    "                   smb2_command_cb cb, void *cb_data)\n"
    "{\n"
    "        return smb2_new_name_async(smb2, oldpath, newpath,\n"
    "                                   SMB2_FILE_RENAME_INFORMATION,\n"
    "                                   SMB2_GENERIC_READ |\n"
    "                                   SMB2_FILE_READ_ATTRIBUTES |\n"
    "                                   SMB2_DELETE,\n"
    "                                   (flags & SMB2_RENAME_REPLACE_IF_EXISTS) ? 1 : 0,\n"
    "                                   cb, cb_data);\n"
    "}\n"
    "\n"
    "int\n"
    "smb2_rename_async(struct smb2_context *smb2, const char *oldpath,\n"
    "                  const char *newpath, smb2_command_cb cb, void *cb_data)\n"
    "{\n"
    "        return smb2_rename2_async(smb2, oldpath, newpath, 0, cb, cb_data);\n"
    "}\n",
)
patch(
    "lib/libsmb2.c",
    "                                   SMB2_FILE_LINK_INFORMATION,\n"
    "                                   SMB2_FILE_READ_ATTRIBUTES,\n"
    "                                   cb, cb_data);\n",
    "                                   SMB2_FILE_LINK_INFORMATION,\n"
    "                                   SMB2_FILE_READ_ATTRIBUTES, 0,\n"
    "                                   cb, cb_data);\n",
)

SYNC_IMPL = """
int smb2_rename2(struct smb2_context *smb2, const char *oldpath,
                 const char *newpath, uint32_t flags)
{
        struct sync_cb_data *cb_data;
        int rc = 0;

        cb_data = calloc(1, sizeof(struct sync_cb_data));
        if (cb_data == NULL) {
                smb2_set_error(smb2, "Failed to allocate sync_cb_data");
                return -ENOMEM;
        }

        rc = smb2_rename2_async(smb2, oldpath, newpath, flags,
                                sync_generic_status_cb, cb_data);
        if (rc < 0) {
                goto out;
        }

        rc = wait_for_reply(smb2, cb_data);
        if (rc < 0) {
                cb_data->status = SMB2_STATUS_CANCELLED;
                return rc;
        }

        rc = cb_data->status;
 out:
        free(cb_data);

        return rc;
}
"""

# ── lib/sync.c — sync wrapper, before smb2_symlink() ─────────────────────────
# Inserted at an anchor rather than appended, so the tree is the same
# whichever order the patches run in (patch_utimes.py appends).
patch(
    "lib/sync.c",
    "int smb2_symlink(struct smb2_context *smb2, const char *target,\n",
    SYNC_IMPL.lstrip("\n") + "\n"
    "int smb2_symlink(struct smb2_context *smb2, const char *target,\n",
)

# ── lib/libsmb2.syms — export list ───────────────────────────────────────────
patch(
    "lib/libsmb2.syms",
    "smb2_rename_async\n",
    "smb2_rename_async\nsmb2_rename2\nsmb2_rename2_async\n",
)

for relpath, content in files.items():
    with open(os.path.join(root, relpath), "w") as f:
        f.write(content)

print("Patched: smb2_rename2 / smb2_rename2_async added (libsmb2.h, libsmb2.c, sync.c, libsmb2.syms)")
