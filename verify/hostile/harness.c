/*
 * Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
 * All rights reserved.
 * Use of this source code is governed by BSD 3-Clause license that can be
 * found in the LICENSE file.
 *
 * Harness for the hostile-server / mutating-proxy runs: the sync libsmb2 API
 * dart_smb2 binds, one sequence per run.
 *
 *   harness <host[:port]> <share> <dir> [ops] [timeout_s] [version]
 *   harness fixture-create|fixture-remove <host[:port]> <share> <dir>
 *
 * ops: letters, run in the order given:
 *   d opendir/readdir/closedir   s stat          o open (O_RDWR|O_CREAT)
 *   r pread (1, 100, 4096, 65536, 200000, max_read)   w pwrite   f fstat
 *   t ftruncate  y fsync  c close   k readlink   v statvfs
 *   e echo   m mkdir/rmdir   u unlink   n rename2   i utimes
 *   E share enum (own context on IPC$, before the rest)
 * Exit code 0 whenever the library returned (errors are printed);
 * sanitizer reports abort the process.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <smb2/smb2.h>
#include <smb2/libsmb2.h>
#include <smb2/libsmb2-raw.h>
#include <smb2/libsmb2-share-enum.h>

static const char *host, *share, *dir;
static int timeout_s = 3;
static int version = 0;

static struct smb2_context *ctx_new(void)
{
        struct smb2_context *smb2 = smb2_init_context();
        if (!smb2) { printf("init_context failed\n"); exit(0); }
        smb2_set_user(smb2, "testuser");
        smb2_set_password(smb2, "testpass");
        smb2_set_timeout(smb2, timeout_s);
        if (version) smb2_set_version(smb2, version);
        if (getenv("H_SIGN")) smb2_set_sign(smb2, 1);
        if (getenv("H_SEAL")) smb2_set_seal(smb2, 1);
        return smb2;
}

#define R(name, rc) printf("  %-10s rc=%d %s\n", name, (int)(rc), (rc) < 0 ? smb2_get_error(smb2) : "")

static void share_enum(void)
{
        struct smb2_context *smb2 = ctx_new();
        int rc = smb2_connect_share(smb2, host, "IPC$", "testuser");
        R("connectIPC", rc);
        if (rc == 0) {
                struct smb2_share_enum_reply *rep =
                        smb2_share_enum_sync(smb2, SMB2_SHARE_INFO_1);
                if (!rep) {
                        printf("  share_enum rc=-1 %s\n", smb2_get_error(smb2));
                } else {
                        uint32_t i, nulls = 0;
                        size_t tot = 0;
                        /* what the Dart side does: read every name and remark */
                        for (i = 0; i < rep->entries_read && rep->share_info.info_1; i++) {
                                if (rep->share_info.info_1[i].netname)
                                        tot += strlen(rep->share_info.info_1[i].netname);
                                else nulls++;
                                if (rep->share_info.info_1[i].remark)
                                        tot += strlen(rep->share_info.info_1[i].remark);
                                else nulls++;
                        }
                        printf("  share_enum rc=0 entries=%u strlen=%zu nullptrs=%u array=%s\n",
                               rep->entries_read, tot, nulls,
                               rep->share_info.info_1 ? "set" : "NULL");
                        smb2_free_data(smb2, rep);
                }
                smb2_disconnect_share(smb2);
        }
        smb2_destroy_context(smb2);
}

static int fixture(int create)
{
        static unsigned char b[300000];
        const char *names[] = {"file.bin", "file2.bin", "link", "gone.bin",
                "entry-0-with-a-longer-name.txt", "entry-1-with-a-longer-name.txt",
                "entry-2-with-a-longer-name.txt"};
        struct smb2_context *smb2 = ctx_new();
        struct smb2fh *f;
        char p[512];
        int i, o = 0, rc;

        if (smb2_connect_share(smb2, host, share, "testuser") < 0) {
                printf("fixture: %s\n", smb2_get_error(smb2));
                return 1;
        }
        if (create) {
                smb2_mkdir(smb2, dir);
                snprintf(p, sizeof p, "%s/file.bin", dir);
                f = smb2_open(smb2, p, O_RDWR | O_CREAT);
                if (!f) { printf("fixture: %s\n", smb2_get_error(smb2)); return 1; }
                for (i = 0; i < 300000; i++) b[i] = (unsigned char)(i * 7);
                while (o < 300000) {
                        int n = smb2_pwrite(smb2, f, b + o, 300000 - o, o);
                        if (n <= 0) break;
                        o += n;
                }
                smb2_ftruncate(smb2, f, 300000);
                smb2_close(smb2, f);
                snprintf(p, sizeof p, "%s/link", dir);
                smb2_symlink(smb2, "file.bin", p, 0);
                for (i = 4; i < 7; i++) {
                        snprintf(p, sizeof p, "%s/%s", dir, names[i]);
                        f = smb2_open(smb2, p, O_RDWR | O_CREAT);
                        if (f) smb2_close(smb2, f);
                }
                printf("fixture created (%d bytes)\n", o);
        } else {
                for (i = 0; i < 7; i++) {
                        snprintf(p, sizeof p, "%s/%s", dir, names[i]);
                        smb2_unlink(smb2, p);
                }
                snprintf(p, sizeof p, "%s/sub", dir);
                smb2_rmdir(smb2, p);
                rc = smb2_rmdir(smb2, dir);
                printf("fixture removed rc=%d %s\n", rc, rc < 0 ? smb2_get_error(smb2) : "");
        }
        smb2_disconnect_share(smb2);
        smb2_destroy_context(smb2);
        return 0;
}

int main(int argc, char **argv)
{
        const char *ops = "dsorwfcklve";
        char path[512], path2[512];
        struct smb2_context *smb2;
        struct smb2fh *fh = NULL;
        const char *p;
        int rc;

        setvbuf(stdout, NULL, _IOLBF, 0);
        /* as the Dart VM does; libsmb2 writes with writev(), no MSG_NOSIGNAL */
        if (!getenv("H_SIGPIPE")) signal(SIGPIPE, SIG_IGN);
        if (argc >= 5 && !strncmp(argv[1], "fixture-", 8)) {
                host = argv[2]; share = argv[3]; dir = argv[4];
                timeout_s = 10;
                return fixture(!strcmp(argv[1], "fixture-create"));
        }
        if (argc < 4) { fprintf(stderr, "usage\n"); return 2; }
        host = argv[1]; share = argv[2]; dir = argv[3];
        if (argc > 4) ops = argv[4];
        if (argc > 5) timeout_s = atoi(argv[5]);
        if (argc > 6) version = (int)strtol(argv[6], NULL, 0);

        if (strchr(ops, 'E')) share_enum();
        if (!strcmp(ops, "E")) { printf("  done\n"); return 0; }

        smb2 = ctx_new();
        rc = smb2_connect_share(smb2, host, share, "testuser");
        R("connect", rc);
        if (rc < 0) { smb2_destroy_context(smb2); printf("  done\n"); return 0; }
        printf("  max_read=%u max_write=%u\n", smb2_get_max_read_size(smb2),
               smb2_get_max_write_size(smb2));

        snprintf(path, sizeof path, "%s/file.bin", dir);
        for (p = ops; *p; p++) {
                switch (*p) {
                case 'd': {
                        struct smb2dir *d = smb2_opendir(smb2, dir);
                        struct smb2dirent *e; int n = 0; size_t tot = 0; uint64_t sz = 0;
                        if (!d) { printf("  opendir    rc=-1 %s\n", smb2_get_error(smb2)); break; }
                        while ((e = smb2_readdir(smb2, d)) != NULL) {
                                n++; tot += strlen(e->name); sz += e->st.smb2_size;
                        }
                        printf("  readdir    rc=0 n=%d namebytes=%zu size=%" PRIu64 "\n", n, tot, sz);
                        smb2_closedir(smb2, d);
                        break; }
                case 's': {
                        struct smb2_stat_64 st; memset(&st, 0, sizeof st);
                        rc = smb2_stat(smb2, path, &st); R("stat", rc);
                        if (rc == 0) printf("    size=%" PRIu64 " type=%u mtime=%" PRIu64 "\n",
                                            st.smb2_size, st.smb2_type, st.smb2_mtime);
                        break; }
                case 'o':
                        fh = smb2_open(smb2, path, O_RDWR | O_CREAT);
                        if (!fh) printf("  open       rc=-1 %s\n", smb2_get_error(smb2));
                        else printf("  open       rc=0\n");
                        break;
                case 'r': {
                        uint32_t sizes[] = {1, 100, 4096, 65536, 200000, 0};
                        int i;
                        if (!fh) break;
                        sizes[5] = smb2_get_max_read_size(smb2);
                        for (i = 0; i < 6; i++) {
                                /* exact-size heap buffer: ASan sees any byte past it */
                                uint32_t want = sizes[i] ? sizes[i] : 1;
                                uint8_t *buf = malloc(want);
                                rc = smb2_pread(smb2, fh, buf, want, 0);
                                printf("  pread(%u) rc=%d %s%s\n", want, rc,
                                       rc < 0 ? smb2_get_error(smb2) : "",
                                       rc > 0 && (uint32_t)rc > want ? " OVERRUN-REPORTED" : "");
                                if (rc > 0 && (uint32_t)rc <= want) {
                                        volatile uint8_t x = 0; int j;
                                        for (j = 0; j < rc; j++) x ^= buf[j];
                                        (void)x;
                                }
                                free(buf);
                        }
                        break; }
                case 'w': {
                        uint32_t sizes[] = {1, 4096, 70000};
                        int i;
                        if (!fh) break;
                        for (i = 0; i < 3; i++) {
                                uint8_t *buf = malloc(sizes[i]);
                                memset(buf, 'A' + i, sizes[i]);
                                rc = smb2_pwrite(smb2, fh, buf, sizes[i], 0);
                                printf("  pwrite(%u) rc=%d %s%s\n", sizes[i], rc,
                                       rc < 0 ? smb2_get_error(smb2) : "",
                                       rc > 0 && (uint32_t)rc > sizes[i] ? " OVERRUN-REPORTED" : "");
                                free(buf);
                        }
                        break; }
                case 'f': {
                        struct smb2_stat_64 st; memset(&st, 0, sizeof st);
                        if (!fh) break;
                        rc = smb2_fstat(smb2, fh, &st); R("fstat", rc);
                        break; }
                case 't':
                        if (!fh) break;
                        rc = smb2_ftruncate(smb2, fh, 300000); R("ftruncate", rc);
                        break;
                case 'y':
                        if (!fh) break;
                        rc = smb2_fsync(smb2, fh); R("fsync", rc);
                        break;
                case 'c':
                        if (!fh) break;
                        rc = smb2_close(smb2, fh); R("close", rc); fh = NULL;
                        break;
                case 'k': {
                        /* as the Dart side: zeroed buffer, one byte more than told */
                        uint32_t len = 4096;
                        char *buf = calloc(1, len + 1);
                        snprintf(path2, sizeof path2, "%s/link", dir);
                        rc = smb2_readlink(smb2, path2, buf, len); R("readlink", rc);
                        if (rc == 0) printf("    target len=%zu\n", strlen(buf));
                        free(buf);
                        break; }
                case 'v': {
                        struct smb2_statvfs vfs; memset(&vfs, 0, sizeof vfs);
                        rc = smb2_statvfs(smb2, dir, &vfs); R("statvfs", rc);
                        if (rc == 0) printf("    bsize=%u blocks=%" PRIu64 "\n", vfs.f_bsize, (uint64_t)vfs.f_blocks);
                        break; }
                case 'e':
                        rc = smb2_echo(smb2); R("echo", rc);
                        break;
                case 'm':
                        snprintf(path2, sizeof path2, "%s/sub", dir);
                        rc = smb2_mkdir(smb2, path2); R("mkdir", rc);
                        rc = smb2_rmdir(smb2, path2); R("rmdir", rc);
                        break;
                case 'n':
                        snprintf(path2, sizeof path2, "%s/file2.bin", dir);
                        rc = smb2_rename2(smb2, path, path2, 1); R("rename2", rc);
                        rc = smb2_rename2(smb2, path2, path, 1); R("rename2b", rc);
                        break;
                case 'i':
                        rc = smb2_utimes(smb2, path, 1700000000000000ULL, 1700000000000000ULL); R("utimes", rc);
                        break;
                case 'u':
                        snprintf(path2, sizeof path2, "%s/gone.bin", dir);
                        rc = smb2_unlink(smb2, path2); R("unlink", rc);
                        break;
                default: break;
                }
        }
        if (fh) { rc = smb2_close(smb2, fh); R("close", rc); }
        rc = smb2_disconnect_share(smb2); R("disconnect", rc);
        smb2_destroy_context(smb2);
        printf("  done\n");
        return 0;
}
