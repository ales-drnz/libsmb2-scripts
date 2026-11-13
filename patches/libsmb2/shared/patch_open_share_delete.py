# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Add smb2_open2 / smb2_open2_async — an open that may share delete.

smb2_open() asks for FILE_SHARE_READ and FILE_SHARE_WRITE: while the file
is open, nobody else can delete or rename it. That is right for a file of
the user's, and wrong for a temporary file the caller writes and then
renames into place. When the connection dies under such a write, the
server keeps the handle of the dead session until it notices, which with a
server that hangs may be never; the caller reconnects, finishes the file
over the new connection, and its rename, or the delete that cleans up, is
refused with STATUS_SHARING_VIOLATION by its own orphaned handle.
dart_smb2 opens the temporary files of its uploads and copies this way.

smb2_open2() takes open2 flags; SMB2_OPEN_SHARE_DELETE adds
FILE_SHARE_DELETE to the share access of that one open, also when the open
is reissued for the target of a symlink. smb2_open() and every other open
keep the share access they had.

Touches:
  include/smb2/libsmb2.h  — SMB2_OPEN_SHARE_DELETE, declarations
  lib/libsmb2.c           — the open2 flags through the open helper
  lib/sync.c              — smb2_open2 sync wrapper
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


def patch(relpath, old, new, count=1):
    if relpath not in files:
        with open(os.path.join(root, relpath)) as f:
            files[relpath] = f.read()
    content = files[relpath]
    if content.count(old) != count:
        print(
            f"ERROR: anchor not found exactly {count} time(s) in {relpath} "
            "(upstream drifted?)"
        )
        sys.exit(1)
    files[relpath] = content.replace(old, new)


# Already applied (a second run on the same tree): nothing to do.
with open(os.path.join(root, "include/smb2/libsmb2.h")) as f:
    if "SMB2_OPEN_SHARE_DELETE" in f.read():
        print("Already patched: smb2_open2 / smb2_open2_async")
        sys.exit(0)


# ── include/smb2/libsmb2.h — public declarations ─────────────────────────────
patch(
    "include/smb2/libsmb2.h",
    "struct smb2fh *smb2_open(struct smb2_context *smb2, const char *path, int flags);\n",
    "struct smb2fh *smb2_open(struct smb2_context *smb2, const char *path, int flags);\n"
    "\n"
    "/*\n"
    " * Flags for smb2_open2()\n"
    " */\n"
    "/*\n"
    " * Let others delete or rename the file while this handle is open\n"
    " * (FILE_SHARE_DELETE), which smb2_open() does not. For a temporary file\n"
    " * of the caller's own: a handle the server still holds for a connection\n"
    " * that died then does not stop the caller from renaming or removing it\n"
    " * over a new one.\n"
    " */\n"
    "#define SMB2_OPEN_SHARE_DELETE 0x00000001\n"
    "\n"
    "/*\n"
    " * Async open2(): smb2_open_async() with open2 flags.\n"
    " *\n"
    " * Returns\n"
    " *  0     : The operation was initiated. Result of the operation will be\n"
    " *          reported through the callback function.\n"
    " * -errno : There was an error. The callback function will not be invoked.\n"
    " *\n"
    " * When the callback is invoked, status indicates the result:\n"
    " *      0 : Success.\n"
    " *          Command_data is struct smb2fh.\n"
    " *          This structure is freed using smb2_close().\n"
    " * -errno : An error occurred.\n"
    " *          Command_data is NULL.\n"
    " */\n"
    "int smb2_open2_async(struct smb2_context *smb2, const char *path, int flags,\n"
    "                     uint32_t open2_flags,\n"
    "                     smb2_command_cb cb, void *cb_data);\n"
    "\n"
    "/*\n"
    " * smb2_open_async_pdu() with open2 flags.\n"
    " */\n"
    "struct smb2_pdu *\n"
    "smb2_open2_async_pdu(struct smb2_context *smb2, const char *path, int flags,\n"
    "                     uint32_t open2_flags,\n"
    "                     smb2_command_cb cb, void *cb_data, void (*free_cb)(void *));\n"
    "\n"
    "/*\n"
    " * Sync open2()\n"
    " *\n"
    " * Returns NULL on failure.\n"
    " */\n"
    "struct smb2fh *smb2_open2(struct smb2_context *smb2, const char *path, int flags,\n"
    "                          uint32_t open2_flags);\n",
)

# ── lib/libsmb2.c — the flags are kept with the handle ───────────────────────
patch(
    "lib/libsmb2.c",
    "        char *path;\n"
    "        int flags;\n"
    "        int symlink_hops;\n",
    "        char *path;\n"
    "        int flags;\n"
    "        /* SMB2_OPEN_* of smb2_open2(), for the retry on a symlink too */\n"
    "        uint32_t open2_flags;\n"
    "        int symlink_hops;\n",
)

# The share access of an open, after open_flags_to_create_request().
patch(
    "lib/libsmb2.c",
    "/*\n"
    " * Follow at most this many links before giving up, so that a loop on the\n"
    " * server can not spin us forever.\n"
    " */\n",
    "/*\n"
    " * Apply the SMB2_OPEN_* flags of smb2_open2() to a create request.\n"
    " */\n"
    "static void\n"
    "open2_flags_to_create_request(struct smb2_create_request *req,\n"
    "                              uint32_t open2_flags)\n"
    "{\n"
    "        if (open2_flags & SMB2_OPEN_SHARE_DELETE) {\n"
    "                req->share_access |= SMB2_FILE_SHARE_DELETE;\n"
    "        }\n"
    "}\n"
    "\n"
    "/*\n"
    " * Follow at most this many links before giving up, so that a loop on the\n"
    " * server can not spin us forever.\n"
    " */\n",
)

# The retry on a symlink asks for the same share access.
patch(
    "lib/libsmb2.c",
    "        open_flags_to_create_request(&req, fh->path, fh->flags,\n"
    "                                     SMB2_OPLOCK_LEVEL_NONE);\n",
    "        open_flags_to_create_request(&req, fh->path, fh->flags,\n"
    "                                     SMB2_OPLOCK_LEVEL_NONE);\n"
    "        open2_flags_to_create_request(&req, fh->open2_flags);\n",
)

# The helper every open goes through takes the flags.
patch(
    "lib/libsmb2.c",
    "                smb2_command_cb cb, void *cb_data, void (*free_cb)(void *),\n"
    "                int caller_frees_pdu)\n"
    "{\n",
    "                smb2_command_cb cb, void *cb_data, void (*free_cb)(void *),\n"
    "                int caller_frees_pdu, uint32_t open2_flags)\n"
    "{\n",
)
patch(
    "lib/libsmb2.c",
    "        fh->cb_data = cb_data;\n"
    "        fh->flags = flags;\n",
    "        fh->cb_data = cb_data;\n"
    "        fh->flags = flags;\n"
    "        fh->open2_flags = open2_flags;\n",
)
patch(
    "lib/libsmb2.c",
    "        open_flags_to_create_request(&req, path, flags, oplock_level);\n",
    "        open_flags_to_create_request(&req, path, flags, oplock_level);\n"
    "        open2_flags_to_create_request(&req, open2_flags);\n",
)

# The opens there were pass no flag.
patch(
    "lib/libsmb2.c",
    "                cb, cb_data, free_cb, 1);\n",
    "                cb, cb_data, free_cb, 1, 0);\n",
)
patch(
    "lib/libsmb2.c",
    "                cb, cb_data, NULL, 0);\n",
    "                cb, cb_data, NULL, 0, 0);\n",
    count=2,
)

# The new entry points, after smb2_open_async().
patch(
    "lib/libsmb2.c",
    "        pdu = _smb2_open_async_with_oplock_or_lease(smb2, path, flags,\n"
    "                SMB2_OPLOCK_LEVEL_NONE, 0, NULL,\n"
    "                cb, cb_data, NULL, 0, 0);\n"
    "        return pdu ? 0 : -1;\n"
    "}\n",
    "        pdu = _smb2_open_async_with_oplock_or_lease(smb2, path, flags,\n"
    "                SMB2_OPLOCK_LEVEL_NONE, 0, NULL,\n"
    "                cb, cb_data, NULL, 0, 0);\n"
    "        return pdu ? 0 : -1;\n"
    "}\n"
    "\n"
    "struct smb2_pdu *\n"
    "smb2_open2_async_pdu(struct smb2_context *smb2, const char *path, int flags,\n"
    "                     uint32_t open2_flags,\n"
    "                     smb2_command_cb cb, void *cb_data, void (*free_cb)(void *))\n"
    "{\n"
    "        return _smb2_open_async_with_oplock_or_lease(smb2, path, flags,\n"
    "                SMB2_OPLOCK_LEVEL_NONE, 0, NULL,\n"
    "                cb, cb_data, free_cb, 1, open2_flags);\n"
    "}\n"
    "\n"
    "int\n"
    "smb2_open2_async(struct smb2_context *smb2, const char *path, int flags,\n"
    "                 uint32_t open2_flags,\n"
    "                 smb2_command_cb cb, void *cb_data)\n"
    "{\n"
    "        struct smb2_pdu *pdu;\n"
    "\n"
    "        pdu = _smb2_open_async_with_oplock_or_lease(smb2, path, flags,\n"
    "                SMB2_OPLOCK_LEVEL_NONE, 0, NULL,\n"
    "                cb, cb_data, NULL, 0, open2_flags);\n"
    "        return pdu ? 0 : -1;\n"
    "}\n",
)

# ── lib/sync.c — sync wrapper, after smb2_open() ─────────────────────────────
patch(
    "lib/sync.c",
    "/*\n"
    " * close()\n"
    " */\n",
    "struct smb2fh *smb2_open2(struct smb2_context *smb2, const char *path, int flags,\n"
    "                          uint32_t open2_flags)\n"
    "{\n"
    "        struct smb2_pdu *pdu;\n"
    "        struct sync_cb_data *cb_data;\n"
    "        void *ptr;\n"
    "\n"
    "        cb_data = calloc(1, sizeof(struct sync_cb_data));\n"
    "        if (cb_data == NULL) {\n"
    "                smb2_set_error(smb2, \"Failed to allocate sync_cb_data\");\n"
    "                return NULL;\n"
    "        }\n"
    "\n"
    "        pdu = smb2_open2_async_pdu(smb2, path, flags, open2_flags,\n"
    "                                   sync_open_cb, cb_data, NULL);\n"
    "        if (pdu == NULL) {\n"
    "                smb2_set_error(smb2, \"smb2_open2_async failed\");\n"
    "                free(cb_data);\n"
    "                return NULL;\n"
    "        }\n"
    "\n"
    "        if (wait_for_reply(smb2, cb_data) < 0) {\n"
    "                sync_free_pending_pdu(smb2, pdu);\n"
    "                free(cb_data);\n"
    "                return NULL;\n"
    "        }\n"
    "\n"
    "        ptr = cb_data->ptr;\n"
    "        smb2_free_pdu(smb2, pdu);\n"
    "        free(cb_data);\n"
    "        return ptr;\n"
    "}\n"
    "\n"
    "/*\n"
    " * close()\n"
    " */\n",
)

# ── lib/libsmb2.syms — export list ───────────────────────────────────────────
patch(
    "lib/libsmb2.syms",
    "smb2_open\n",
    "smb2_open\n"
    "smb2_open2\n"
    "smb2_open2_async\n"
    "smb2_open2_async_pdu\n",
)

for relpath, content in files.items():
    with open(os.path.join(root, relpath), "w") as f:
        f.write(content)

print("Patched: smb2_open2 / smb2_open2_async added (libsmb2.h, libsmb2.c, sync.c, libsmb2.syms)")
