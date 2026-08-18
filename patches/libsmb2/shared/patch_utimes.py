# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Add smb2_utimes / smb2_utimes_async — set last-access / last-write time.

Upstream libsmb2 has no public API to set file timestamps. dart_smb2 0.1.1
exposes `setLastModified` / `setLastAccessed` (issue #1), implemented on top
of this API: a compound CREATE(FILE_WRITE_ATTRIBUTES) + SET_INFO
(FILE_BASIC_INFORMATION) + CLOSE round-trip.

Timestamps are microseconds since the Unix epoch; 0 encodes as 0 on the
wire, which per MS-FSCC means "do not change this field" — so either
timestamp can be updated independently.

Touches:
  include/smb2/libsmb2.h  — public declarations (async + sync)
  lib/libsmb2.c           — smb2_utimes_async implementation
  lib/sync.c              — smb2_utimes sync wrapper
  lib/libsmb2.syms        — export list entries
"""
import sys
import os

root = sys.argv[1]


def patch(relpath, old, new, count=1):
    fn = os.path.join(root, relpath)
    with open(fn) as f:
        content = f.read()
    if old not in content:
        print(f"ERROR: anchor not found in {relpath} (upstream drifted?)")
        sys.exit(1)
    with open(fn, "w") as f:
        f.write(content.replace(old, new, count))


# ── include/smb2/libsmb2.h — public declarations ─────────────────────────────
patch(
    "include/smb2/libsmb2.h",
    "int smb2_ftruncate(struct smb2_context *smb2, struct smb2fh *fh,\n"
    "                   uint64_t length);\n",
    "int smb2_ftruncate(struct smb2_context *smb2, struct smb2fh *fh,\n"
    "                   uint64_t length);\n"
    "\n"
    "/*\n"
    " * UTIMES\n"
    " */\n"
    "/*\n"
    " * Async utimes()\n"
    " * Set the last-access and/or last-write time of a file or directory\n"
    " * via SET_INFO / FILE_BASIC_INFORMATION.\n"
    " *\n"
    " * atime_us and mtime_us are microseconds since the Unix epoch.\n"
    " * Pass 0 to leave that timestamp unchanged on the server.\n"
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
    "int smb2_utimes_async(struct smb2_context *smb2, const char *path,\n"
    "                      uint64_t atime_us, uint64_t mtime_us,\n"
    "                      smb2_command_cb cb, void *cb_data);\n"
    "/*\n"
    " * Sync utimes()\n"
    " * Function returns\n"
    " *      0 : Success\n"
    " * -errno : An error occurred.\n"
    " */\n"
    "int smb2_utimes(struct smb2_context *smb2, const char *path,\n"
    "                uint64_t atime_us, uint64_t mtime_us);\n",
)

# ── lib/libsmb2.c — async implementation ─────────────────────────────────────
UTIMES_IMPL = """
struct utimes_cb_data {
        smb2_command_cb cb;
        void *cb_data;

        uint32_t status;
};

static void
utimes_cb_3(struct smb2_context *smb2, int status,
            void *command_data _U_, void *private_data)
{
        struct utimes_cb_data *utimes_data = private_data;

        if (utimes_data->status == SMB2_STATUS_SUCCESS) {
                utimes_data->status = status;
        }

        if (utimes_data->status != SMB2_STATUS_SUCCESS) {
                smb2_set_nterror(smb2, utimes_data->status, "%s",
                                 nterror_to_str(utimes_data->status));
        }

        utimes_data->cb(smb2, -nterror_to_errno(utimes_data->status),
                        NULL, utimes_data->cb_data);
        free(utimes_data);
}

static void
utimes_cb_2(struct smb2_context *smb2, int status,
            void *command_data, void *private_data)
{
        struct utimes_cb_data *utimes_data = private_data;

        if (utimes_data->status == SMB2_STATUS_SUCCESS) {
                utimes_data->status = status;
        }
}

static void
utimes_cb_1(struct smb2_context *smb2, int status,
            void *command_data _U_, void *private_data)
{
        struct utimes_cb_data *utimes_data = private_data;

        if (utimes_data->status == SMB2_STATUS_SUCCESS) {
                utimes_data->status = status;
        }
}

int
smb2_utimes_async(struct smb2_context *smb2, const char *path,
                  uint64_t atime_us, uint64_t mtime_us,
                  smb2_command_cb cb, void *cb_data)
{
        struct utimes_cb_data *utimes_data;
        struct smb2_create_request cr_req;
        struct smb2_set_info_request si_req;
        struct smb2_close_request cl_req;
        struct smb2_pdu *pdu, *next_pdu;
        struct smb2_file_basic_info fbi _U_;

        if (smb2 == NULL) {
                return -EINVAL;
        }

        utimes_data = calloc(1, sizeof(struct utimes_cb_data));
        if (utimes_data == NULL) {
                smb2_set_error(smb2, "Failed to allocate utimes_data");
                return -ENOMEM;
        }

        utimes_data->cb = cb;
        utimes_data->cb_data = cb_data;

        /* CREATE command */
        memset(&cr_req, 0, sizeof(struct smb2_create_request));
        cr_req.requested_oplock_level = SMB2_OPLOCK_LEVEL_NONE;
        cr_req.impersonation_level = SMB2_IMPERSONATION_IMPERSONATION;
        cr_req.desired_access = SMB2_FILE_WRITE_ATTRIBUTES;
        cr_req.file_attributes = 0;
        cr_req.share_access = SMB2_FILE_SHARE_READ | SMB2_FILE_SHARE_WRITE;
        cr_req.create_disposition = SMB2_FILE_OPEN;
        cr_req.create_options = 0;
        cr_req.name = path;

        pdu = smb2_cmd_create_async(smb2, &cr_req, utimes_cb_1, utimes_data);
        if (pdu == NULL) {
                smb2_set_error(smb2, "Failed to create create command");
                free(utimes_data);
                return -EINVAL;
        }

        /* SET INFO command.
         * A timestamp of 0 encodes as 0 on the wire, which per MS-FSCC
         * means "do not change this field". creation/change time and
         * file_attributes stay 0 and are never touched. */
        memset(&fbi, 0, sizeof(struct smb2_file_basic_info));
        fbi.last_access_time.tv_sec = (time_t)(atime_us / 1000000);
        fbi.last_access_time.tv_usec = (long)(atime_us % 1000000);
        fbi.last_write_time.tv_sec = (time_t)(mtime_us / 1000000);
        fbi.last_write_time.tv_usec = (long)(mtime_us % 1000000);

        memset(&si_req, 0, sizeof(struct smb2_set_info_request));
        si_req.info_type = SMB2_0_INFO_FILE;
        si_req.file_info_class = SMB2_FILE_BASIC_INFORMATION;
        si_req.additional_information = 0;
        memcpy(si_req.file_id, compound_file_id, SMB2_FD_SIZE);
        si_req.input_data = &fbi;

        next_pdu = smb2_cmd_set_info_async(smb2, &si_req,
                                           utimes_cb_2, utimes_data);
        if (next_pdu == NULL) {
                smb2_set_error(smb2, "Failed to create set command. %s",
                               smb2_get_error(smb2));
                free(utimes_data);
                smb2_free_pdu(smb2, pdu);
                return -EINVAL;
        }
        smb2_add_compound_pdu(smb2, pdu, next_pdu);

        /* CLOSE command */
        memset(&cl_req, 0, sizeof(struct smb2_close_request));
        cl_req.flags = SMB2_CLOSE_FLAG_POSTQUERY_ATTRIB;
        memcpy(cl_req.file_id, compound_file_id, SMB2_FD_SIZE);

        next_pdu = smb2_cmd_close_async(smb2, &cl_req, utimes_cb_3,
                                        utimes_data);
        if (next_pdu == NULL) {
                utimes_data->cb(smb2, -ENOMEM, NULL, utimes_data->cb_data);
                free(utimes_data);
                smb2_free_pdu(smb2, pdu);
                return -EINVAL;
        }
        smb2_add_compound_pdu(smb2, pdu, next_pdu);

        smb2_queue_pdu(smb2, pdu);

        return 0;
}

"""

patch(
    "lib/libsmb2.c",
    "/* *new_name* is used for both renaming and creating hard links */\n",
    UTIMES_IMPL + "/* *new_name* is used for both renaming and creating hard links */\n",
)

# ── lib/sync.c — sync wrapper (appended at end of file) ──────────────────────
SYNC_IMPL = """
int smb2_utimes(struct smb2_context *smb2, const char *path,
                uint64_t atime_us, uint64_t mtime_us)
{
        struct sync_cb_data *cb_data;
        int rc = 0;

        cb_data = calloc(1, sizeof(struct sync_cb_data));
        if (cb_data == NULL) {
                smb2_set_error(smb2, "Failed to allocate sync_cb_data");
                return -ENOMEM;
        }

        rc = smb2_utimes_async(smb2, path, atime_us, mtime_us,
                               sync_generic_status_cb, cb_data);
        if (rc < 0) {
                goto out;
        }

        rc = wait_for_reply(smb2, cb_data);
        if (rc < 0) {
                cb_data->status = SMB2_STATUS_CANCELLED;
                return rc;
        }

        rc = (int)cb_data->status;
 out:
        free(cb_data);

        return rc;
}
"""

fn = os.path.join(root, "lib/sync.c")
with open(fn) as f:
    sync_src = f.read()
for needed in ("sync_generic_status_cb", "wait_for_reply"):
    if needed not in sync_src:
        print(f"ERROR: lib/sync.c no longer has {needed} (upstream drifted?)")
        sys.exit(1)
with open(fn, "a") as f:
    f.write(SYNC_IMPL)

# ── lib/libsmb2.syms — export list ───────────────────────────────────────────
patch(
    "lib/libsmb2.syms",
    "smb2_truncate_async\n",
    "smb2_truncate_async\nsmb2_utimes\nsmb2_utimes_async\n",
)

print("Patched: smb2_utimes / smb2_utimes_async added (libsmb2.h, libsmb2.c, sync.c, libsmb2.syms)")
