# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Make rmdir report a directory that is not empty.

smb2_rmdir_async() opens the directory with FILE_DELETE_ON_CLOSE and
closes it. For a directory that still has entries the server accepts both
the create and the close and simply does not delete it ([MS-FSA] 2.1.5.4),
so rmdir() returned 0 while the directory stayed. dart_smb2's integration
suite caught it against Samba 4.23.

rmdir now sends CREATE (DELETE access, directory, the reparse point
itself) + SET_INFO FileDispositionInformation(DeletePending = 1) + CLOSE,
the way Windows' RemoveDirectory does: the SET_INFO answers
STATUS_DIRECTORY_NOT_EMPTY, which reaches the caller as -ENOTEMPTY with
the NT status recorded.

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
    "int\n"
    "smb2_rmdir_async(struct smb2_context *smb2, const char *path,\n"
    "                 smb2_command_cb cb, void *cb_data)\n"
    "{\n"
    "        return smb2_unlink_internal(smb2, path, 1, cb, cb_data);\n"
    "}\n"
)

new = r'''/* dart_smb2: rmdir through FileDispositionInformation, so a directory
 * that is not empty fails instead of silently staying (see
 * patch_rmdir_disposition.py). */
struct rmdir_cb_data {
        smb2_command_cb cb;
        void *cb_data;
        uint32_t status;
};

static void
rmdir_cb_status(struct smb2_context *smb2 _U_, int status,
                void *command_data _U_, void *private_data)
{
        struct rmdir_cb_data *rmdir_data = private_data;

        if (rmdir_data->status == SMB2_STATUS_SUCCESS) {
                rmdir_data->status = status;
        }
}

static void
rmdir_cb_close(struct smb2_context *smb2, int status,
               void *command_data _U_, void *private_data)
{
        struct rmdir_cb_data *rmdir_data = private_data;

        if (rmdir_data->status == SMB2_STATUS_SUCCESS) {
                rmdir_data->status = status;
        }
        if (rmdir_data->status != SMB2_STATUS_SUCCESS) {
                smb2_set_nterror(smb2, rmdir_data->status,
                                 "Rmdir failed with (0x%08x) %s.",
                                 rmdir_data->status,
                                 nterror_to_str(rmdir_data->status));
        }
        rmdir_data->cb(smb2, -nterror_to_errno(rmdir_data->status),
                       NULL, rmdir_data->cb_data);
        free(rmdir_data);
}

int
smb2_rmdir_async(struct smb2_context *smb2, const char *path,
                 smb2_command_cb cb, void *cb_data)
{
        struct rmdir_cb_data *rmdir_data;
        struct smb2_create_request cr_req;
        struct smb2_set_info_request si_req;
        struct smb2_close_request cl_req;
        struct smb2_file_disposition_info fdi;
        struct smb2_pdu *pdu, *next_pdu;

        if (smb2 == NULL) {
                return -EINVAL;
        }

        rmdir_data = calloc(1, sizeof(struct rmdir_cb_data));
        if (rmdir_data == NULL) {
                smb2_set_error(smb2, "Failed to allocate rmdir_data");
                return -ENOMEM;
        }
        rmdir_data->cb = cb;
        rmdir_data->cb_data = cb_data;

        memset(&cr_req, 0, sizeof(struct smb2_create_request));
        cr_req.requested_oplock_level = SMB2_OPLOCK_LEVEL_NONE;
        cr_req.impersonation_level = SMB2_IMPERSONATION_IMPERSONATION;
        cr_req.desired_access = SMB2_DELETE;
        cr_req.file_attributes = SMB2_FILE_ATTRIBUTE_DIRECTORY;
        cr_req.share_access = SMB2_FILE_SHARE_READ | SMB2_FILE_SHARE_WRITE |
                SMB2_FILE_SHARE_DELETE;
        cr_req.create_disposition = SMB2_FILE_OPEN;
        cr_req.create_options = SMB2_FILE_DIRECTORY_FILE |
                SMB2_FILE_OPEN_REPARSE_POINT;
        cr_req.name = path;

        pdu = smb2_cmd_create_async(smb2, &cr_req, rmdir_cb_status,
                                    rmdir_data);
        if (pdu == NULL) {
                smb2_set_error(smb2, "Failed to create create command");
                free(rmdir_data);
                return -ENOMEM;
        }

        fdi.delete_pending = 1;
        memset(&si_req, 0, sizeof(struct smb2_set_info_request));
        si_req.info_type = SMB2_0_INFO_FILE;
        si_req.file_info_class = SMB2_FILE_DISPOSITION_INFORMATION;
        memcpy(si_req.file_id, compound_file_id, SMB2_FD_SIZE);
        si_req.input_data = &fdi;

        next_pdu = smb2_cmd_set_info_async(smb2, &si_req, rmdir_cb_status,
                                           rmdir_data);
        if (next_pdu == NULL) {
                smb2_set_error(smb2, "Failed to create set-info command");
                smb2_free_pdu(smb2, pdu);
                free(rmdir_data);
                return -ENOMEM;
        }
        smb2_add_compound_pdu(smb2, pdu, next_pdu);

        memset(&cl_req, 0, sizeof(struct smb2_close_request));
        cl_req.flags = SMB2_CLOSE_FLAG_POSTQUERY_ATTRIB;
        memcpy(cl_req.file_id, compound_file_id, SMB2_FD_SIZE);

        next_pdu = smb2_cmd_close_async(smb2, &cl_req, rmdir_cb_close,
                                        rmdir_data);
        if (next_pdu == NULL) {
                smb2_set_error(smb2, "Failed to create close command");
                smb2_free_pdu(smb2, pdu);
                free(rmdir_data);
                return -ENOMEM;
        }
        smb2_add_compound_pdu(smb2, pdu, next_pdu);

        smb2_queue_pdu(smb2, pdu);

        return 0;
}
'''

if content.count(old) != 1:
    print("ERROR: smb2_rmdir_async anchor not found exactly once in lib/libsmb2.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/libsmb2.c: rmdir sets FileDispositionInformation and reports its status")
