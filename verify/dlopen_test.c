/*
 * Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
 * All rights reserved.
 * Use of this source code is governed by BSD 3-Clause license that can be
 * found in the LICENSE file.
 *
 * dlopen smoke test for the built libsmb2 shared library.
 *
 * Loads the .so/.dylib given as argv[1] and resolves the symbols the
 * dart_smb2 FFI layer binds at runtime — both the smb2w_* wrapper API and
 * the patched-in libsmb2 additions. Exits non-zero (naming the first
 * missing symbol) on failure.
 *
 *   cc verify/dlopen_test.c -o dlopen_test -ldl
 *   ./dlopen_test release_builds/libsmb2_linux-x86_64.so
 */
#include <stdio.h>
#include <dlfcn.h>

static const char *symbols[] = {
    /* wrapper lifecycle + errors */
    "smb2w_connect",
    "smb2w_disconnect",
    "smb2w_echo",
    "smb2w_error",
    "smb2w_get_last_error",
    "smb2w_get_nterror",
    "smb2w_get_errno",
    "smb2w_free",
    /* wrapper file ops */
    "smb2w_open_file",
    "smb2w_open_file_write",
    "smb2w_open_file_with_size",
    "smb2w_close_file",
    "smb2w_read_file",
    "smb2w_write_file",
    "smb2w_pread",
    "smb2w_pread_handle",
    "smb2w_pwrite",
    "smb2w_pwrite_handle",
    "smb2w_filesize",
    "smb2w_fsync",
    "smb2w_ftruncate",
    "smb2w_truncate",
    "smb2w_unlink",
    "smb2w_rename",
    "smb2w_stat",
    "smb2w_statvfs",
    "smb2w_readlink",
    /* wrapper directory ops */
    "smb2w_listdir",
    "smb2w_dirlist_free",
    "smb2w_mkdir",
    "smb2w_rmdir",
    /* wrapper share enumeration */
    "smb2w_list_shares",
    "smb2w_sharelist_free",
    /* patched-in libsmb2 API (bound directly by dart_smb2) */
    "smb2_utimes",
    "smb2_utimes_async",
    /* upstream API the wrapper depends on */
    "smb2_share_enum_sync",
    "smb2_init_context",
    "smb2_destroy_context",
    NULL,
};

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s <libsmb2.so>\n", argv[0]);
        return 2;
    }

    void *h = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!h) {
        fprintf(stderr, "FAIL dlopen: %s\n", dlerror());
        return 1;
    }

    int missing = 0;
    for (const char **s = symbols; *s; s++) {
        if (!dlsym(h, *s)) {
            fprintf(stderr, "FAIL missing symbol: %s\n", *s);
            missing++;
        }
    }
    dlclose(h);

    if (missing) {
        fprintf(stderr, "FAIL %d symbol(s) missing in %s\n", missing, argv[1]);
        return 1;
    }
    printf("OK %s: dlopen + all %d symbols resolved\n",
           argv[1], (int)(sizeof(symbols) / sizeof(symbols[0]) - 1));
    return 0;
}
