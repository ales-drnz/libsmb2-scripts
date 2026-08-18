/*
 * smb2_wrapper.c — C wrapper around libsmb2 for Dart FFI.
 *
 * Exposes a simple, flat API that is safe to call from Dart's FFI layer.
 * All functions are synchronous (blocking) — call from a Dart isolate
 * to avoid blocking the UI thread.
 *
 * Compiled as a shared library (dylib/so) with libsmb2 statically linked.
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <time.h>
#include <smb2/smb2.h>
#include <smb2/libsmb2.h>
#include <smb2/libsmb2-raw.h>
#include <smb2/libsmb2-share-enum.h>

/* ────────────────────────────────────────────────────────────────────────────
 * Windows: initialise Winsock when the DLL is loaded so callers (including
 * standalone Dart test processes) do not need to call WSAStartup themselves.
 * ──────────────────────────────────────────────────────────────────────────── */
#if defined(_WIN32) || defined(_WINDOWS)
#include <winsock2.h>
#include <windows.h>

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)hinstDLL; (void)lpvReserved;
    static WSADATA wsa_data;
    switch (fdwReason) {
        case DLL_PROCESS_ATTACH:
            if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) return FALSE;
            break;
        case DLL_PROCESS_DETACH:
            WSACleanup();
            break;
    }
    return TRUE;
}
#endif

/* ────────────────────────────────────────────────────────────────────────────
 * Global mutex for libsmb2 context lifecycle.
 *
 * libsmb2 maintains a global `active_contexts` linked list (init.c) that is
 * mutated without any locking by smb2_init_context() and smb2_destroy_context().
 * When multiple Dart isolates (OS threads) create or destroy contexts
 * concurrently, this causes a data race that can corrupt the list.
 *
 * We serialize all context creation and destruction behind this mutex.
 * ──────────────────────────────────────────────────────────────────────────── */

#if defined(_WIN32) || defined(_WINDOWS)

static SRWLOCK smb2w_ctx_lock = SRWLOCK_INIT;

static void smb2w_lock(void)   { AcquireSRWLockExclusive(&smb2w_ctx_lock); }
static void smb2w_unlock(void) { ReleaseSRWLockExclusive(&smb2w_ctx_lock); }

#else

#include <pthread.h>
static pthread_mutex_t smb2w_ctx_lock = PTHREAD_MUTEX_INITIALIZER;

static void smb2w_lock(void)   { pthread_mutex_lock(&smb2w_ctx_lock); }
static void smb2w_unlock(void) { pthread_mutex_unlock(&smb2w_ctx_lock); }

#endif

/* ────────────────────────────────────────────────────────────────────────────
 * Error tracking
 * ──────────────────────────────────────────────────────────────────────────── */

#if defined(_MSC_VER)
static __declspec(thread) char smb2w_last_error[512] = {0};
#else
static _Thread_local char smb2w_last_error[512] = {0};
#endif

const char *smb2w_get_last_error(void) {
    return smb2w_last_error;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Connection
 * ──────────────────────────────────────────────────────────────────────────── */

struct smb2_context *smb2w_connect(
    const char *host,
    const char *share,
    const char *user,
    const char *password,
    const char *domain,
    int timeout_sec,
    int seal,
    int signing,
    int version
) {
    smb2w_last_error[0] = '\0';

    smb2w_lock();
    struct smb2_context *ctx = smb2_init_context();
    smb2w_unlock();

    if (!ctx) {
        snprintf(smb2w_last_error, sizeof(smb2w_last_error),
                 "Failed to create SMB2 context");
        return NULL;
    }

    if (user && user[0])         smb2_set_user(ctx, user);
    if (password && password[0]) smb2_set_password(ctx, password);
    if (domain && domain[0])     smb2_set_domain(ctx, domain);
    if (timeout_sec > 0)         smb2_set_timeout(ctx, timeout_sec);
    if (seal)                    smb2_set_seal(ctx, 1);
    if (signing)                 smb2_set_sign(ctx, 1);
    if (version)                 smb2_set_version(ctx, version);

    int rc = smb2_connect_share(ctx, host, share, user);
    if (rc < 0) {
        snprintf(smb2w_last_error, sizeof(smb2w_last_error),
                 "%s", smb2_get_error(ctx));
        smb2w_lock();
        smb2_destroy_context(ctx);
        smb2w_unlock();
        return NULL;
    }
    return ctx;
}

void smb2w_disconnect(struct smb2_context *ctx) {
    if (!ctx) return;
    smb2_disconnect_share(ctx);
    smb2w_lock();
    smb2_destroy_context(ctx);
    smb2w_unlock();
}

const char *smb2w_error(struct smb2_context *ctx) {
    if (!ctx) return smb2w_last_error;
    return smb2_get_error(ctx);
}

/*
 * Return the raw NT status code from the last failed operation.
 * Returns 0 if ctx is NULL (no error).
 */
int32_t smb2w_get_nterror(struct smb2_context *ctx) {
    if (!ctx) return 0;
    return (int32_t)smb2_get_nterror(ctx);
}

/*
 * Return the POSIX errno mapped from the last NT status code.
 * libsmb2 maps NT status → errno via nterror_to_errno() internally.
 * Returns 0 if ctx is NULL (no error).
 */
int32_t smb2w_get_errno(struct smb2_context *ctx) {
    if (!ctx) return 0;
    return (int32_t)nterror_to_errno((uint32_t)smb2_get_nterror(ctx));
}

/* ────────────────────────────────────────────────────────────────────────────
 * Directory listing
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * Flat directory entry — no internal pointers, safe for FFI.
 * Total size: 288 bytes (256 + 4 + padding + 8 + 8 + 8).
 */
struct smb2w_entry {
    char     name[256];
    uint32_t type;       /* 0 = file, 1 = directory, 2 = link */
    uint64_t size;       /* bytes */
    uint64_t mtime;      /* modification time, seconds since epoch */
    uint64_t btime;      /* birth/creation time, seconds since epoch */
};

/* Result of smb2w_listdir(). Free with smb2w_dirlist_free(). */
struct smb2w_dirlist {
    struct smb2w_entry *entries;
    int count;
};

struct smb2w_dirlist *smb2w_listdir(struct smb2_context *ctx, const char *path) {
    if (!ctx) return NULL;

    struct smb2dir *dir = smb2_opendir(ctx, path);
    if (!dir) return NULL;

    int capacity = 128;
    int count = 0;
    struct smb2w_entry *entries = malloc(sizeof(struct smb2w_entry) * capacity);
    if (!entries) { smb2_closedir(ctx, dir); return NULL; }

    struct smb2dirent *ent;
    while ((ent = smb2_readdir(ctx, dir)) != NULL) {
        /* Skip . and .. */
        if (ent->name[0] == '.' &&
            (ent->name[1] == '\0' ||
             (ent->name[1] == '.' && ent->name[2] == '\0')))
            continue;

        if (count >= capacity) {
            if (capacity > INT32_MAX / 2) {
                free(entries); smb2_closedir(ctx, dir); return NULL;
            }
            capacity *= 2;
            struct smb2w_entry *tmp = realloc(entries,
                sizeof(struct smb2w_entry) * capacity);
            if (!tmp) { free(entries); smb2_closedir(ctx, dir); return NULL; }
            entries = tmp;
        }

        strncpy(entries[count].name, ent->name, 255);
        entries[count].name[255] = '\0';
        entries[count].type  = ent->st.smb2_type;
        entries[count].size  = ent->st.smb2_size;
        entries[count].mtime = ent->st.smb2_mtime;
        entries[count].btime = ent->st.smb2_btime;
        count++;
    }

    smb2_closedir(ctx, dir);

    struct smb2w_dirlist *result = malloc(sizeof(struct smb2w_dirlist));
    if (!result) { free(entries); return NULL; }
    result->entries = entries;
    result->count   = count;
    return result;
}

void smb2w_dirlist_free(struct smb2w_dirlist *list) {
    if (!list) return;
    free(list->entries);
    free(list);
}

/* ────────────────────────────────────────────────────────────────────────────
 * File reading — one-shot (opens + reads + closes)
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * Read `length` bytes from `path` at `offset` into caller-provided `buf`.
 * Returns the number of bytes actually read, or -1 on error.
 * Reads in 64 KB chunks for network stability.
 */
int smb2w_pread(
    struct smb2_context *ctx,
    const char *path,
    uint8_t *buf,
    uint32_t length,
    uint64_t offset
) {
    if (!ctx || !path || !buf) return -1;

    struct smb2fh *fh = smb2_open(ctx, path, O_RDONLY);
    if (!fh) return -1;

    /* Use the server-negotiated max read size (often 1-8 MB). */
    uint32_t max_chunk = smb2_get_max_read_size(ctx);
    if (max_chunk == 0) max_chunk = 1048576;

    uint32_t total = 0;
    while (total < length) {
        uint32_t chunk = length - total;
        if (chunk > max_chunk) chunk = max_chunk;
        int n = smb2_pread(ctx, fh, buf + total, chunk, offset + total);
        if (n < 0) { smb2_close(ctx, fh); return -1; }
        if (n == 0) break; /* EOF */
        total += (uint32_t)n;
    }

    smb2_close(ctx, fh);
    return (int)total;
}

/*
 * Read an entire file into a newly allocated buffer.
 * Sets *out_size to the number of bytes read.
 * Returns the buffer (caller must free()), or NULL on error.
 */
uint8_t *smb2w_read_file(
    struct smb2_context *ctx,
    const char *path,
    int64_t *out_size
) {
    if (!ctx || !path || !out_size) return NULL;
    *out_size = 0;

    struct smb2_stat_64 st;
    if (smb2_stat(ctx, path, &st) < 0) return NULL;
    if (st.smb2_type != SMB2_TYPE_FILE) return NULL;

    int64_t size = (int64_t)st.smb2_size;
    if (size < 0) return NULL;
    if (size == 0) { *out_size = 0; return calloc(1, 1); }

    uint8_t *buf = malloc(size);
    if (!buf) return NULL;

    struct smb2fh *fh = smb2_open(ctx, path, O_RDONLY);
    if (!fh) { free(buf); return NULL; }

    uint32_t max_chunk = smb2_get_max_read_size(ctx);
    if (max_chunk == 0) max_chunk = 1048576;

    int64_t total = 0;
    while (total < size) {
        int64_t remaining = size - total;
        uint32_t chunk = remaining > max_chunk ? max_chunk : (uint32_t)remaining;
        int n = smb2_pread(ctx, fh, buf + total, chunk, (uint64_t)total);
        if (n < 0)  { free(buf); smb2_close(ctx, fh); return NULL; }
        if (n == 0) break; /* EOF */
        total += n;
    }

    smb2_close(ctx, fh);
    *out_size = total;
    return buf;
}

/* ────────────────────────────────────────────────────────────────────────────
 * File handles — open once, read many, close once
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * Open a file for reading and return its handle.
 * The caller MUST close the handle with smb2w_close_file().
 */
struct smb2fh *smb2w_open_file(struct smb2_context *ctx, const char *path) {
    if (!ctx || !path) return NULL;
    return smb2_open(ctx, path, O_RDONLY);
}

/*
 * Open a file and return its size in one call.
 * Uses open + fstat on the handle instead of stat + open, avoiding the
 * extra Create+QueryInfo+Close that smb2_stat() performs internally.
 * Returns the file handle, or NULL on error. Sets *out_size.
 */
struct smb2fh *smb2w_open_file_with_size(
    struct smb2_context *ctx,
    const char *path,
    int64_t *out_size
) {
    if (!ctx || !path || !out_size) return NULL;

    struct smb2fh *fh = smb2_open(ctx, path, O_RDONLY);
    if (!fh) return NULL;

    struct smb2_stat_64 st;
    if (smb2_fstat(ctx, fh, &st) < 0) {
        smb2_close(ctx, fh);
        return NULL;
    }
    *out_size = (int64_t)st.smb2_size;
    return fh;
}

/*
 * Read from an open file handle at `offset`.
 * Returns the number of bytes read, or -1 on error.
 */
int smb2w_pread_handle(
    struct smb2_context *ctx,
    struct smb2fh *fh,
    uint8_t *buf,
    uint32_t length,
    uint64_t offset
) {
    if (!ctx || !fh || !buf) return -1;

    uint32_t max_chunk = smb2_get_max_read_size(ctx);
    if (max_chunk == 0) max_chunk = 1048576;

    uint32_t total = 0;
    while (total < length) {
        uint32_t chunk = length - total;
        if (chunk > max_chunk) chunk = max_chunk;
        int n = smb2_pread(ctx, fh, buf + total, chunk, offset + total);
        if (n < 0) return -1;
        if (n == 0) break; /* EOF */
        total += (uint32_t)n;
    }
    return (int)total;
}

/*
 * Close an open file handle.
 */
void smb2w_close_file(struct smb2_context *ctx, struct smb2fh *fh) {
    if (ctx && fh) smb2_close(ctx, fh);
}

/* Free a buffer returned by smb2w_read_file(). */
void smb2w_free(void *ptr) {
    free(ptr);
}

/* ────────────────────────────────────────────────────────────────────────────
 * Share enumeration
 * ──────────────────────────────────────────────────────────────────────────── */

/* Share entry returned to Dart. */
struct smb2w_share_entry {
    char     name[256];
    uint32_t type;  /* SHARE_TYPE_DISKTREE=0, PRINTQ=1, DEVICE=2, IPC=3 */
};

struct smb2w_sharelist {
    struct smb2w_share_entry *entries;
    int count;
};

/*
 * List shares on a server. Connects to IPC$ internally.
 * Returns NULL on failure. Free with smb2w_sharelist_free().
 */
struct smb2w_sharelist *smb2w_list_shares(
    const char *host,
    const char *user,
    const char *password,
    const char *domain,
    int timeout_sec
) {
    smb2w_last_error[0] = '\0';

    smb2w_lock();
    struct smb2_context *ctx = smb2_init_context();
    smb2w_unlock();

    if (!ctx) {
        snprintf(smb2w_last_error, sizeof(smb2w_last_error),
                 "Failed to create context");
        return NULL;
    }

    if (user && user[0])         smb2_set_user(ctx, user);
    if (password && password[0]) smb2_set_password(ctx, password);
    if (domain && domain[0])     smb2_set_domain(ctx, domain);
    if (timeout_sec > 0)         smb2_set_timeout(ctx, timeout_sec);

    /* Connect to IPC$ for DCERPC share enumeration */
    int rc = smb2_connect_share(ctx, host, "IPC$", user);
    if (rc < 0) {
        snprintf(smb2w_last_error, sizeof(smb2w_last_error),
                 "%s", smb2_get_error(ctx));
        smb2w_lock();
        smb2_destroy_context(ctx);
        smb2w_unlock();
        return NULL;
    }

    struct srvsvc_NetrShareEnum_rep *rep =
        smb2_share_enum_sync(ctx, SHARE_INFO_1);
    if (!rep) {
        snprintf(smb2w_last_error, sizeof(smb2w_last_error),
                 "%s", smb2_get_error(ctx));
        smb2_disconnect_share(ctx);
        smb2w_lock();
        smb2_destroy_context(ctx);
        smb2w_unlock();
        return NULL;
    }

    int count = (int)rep->ses.ShareEnum.Level1.EntriesRead;
    struct srvsvc_SHARE_INFO_1 *infos =
        rep->ses.ShareEnum.Level1.share_info_1;

    struct smb2w_share_entry *entries =
        malloc(sizeof(struct smb2w_share_entry) * count);
    if (!entries) {
        smb2_free_data(ctx, rep);
        smb2_disconnect_share(ctx);
        smb2w_lock();
        smb2_destroy_context(ctx);
        smb2w_unlock();
        return NULL;
    }

    for (int i = 0; i < count; i++) {
        const char *name = infos[i].netname;
        if (name) {
            strncpy(entries[i].name, name, 255);
            entries[i].name[255] = '\0';
        } else {
            entries[i].name[0] = '\0';
        }
        entries[i].type = infos[i].type;
    }

    smb2_free_data(ctx, rep);
    smb2_disconnect_share(ctx);
    smb2w_lock();
    smb2_destroy_context(ctx);
    smb2w_unlock();

    struct smb2w_sharelist *result = malloc(sizeof(struct smb2w_sharelist));
    if (!result) { free(entries); return NULL; }
    result->entries = entries;
    result->count = count;
    return result;
}

void smb2w_sharelist_free(struct smb2w_sharelist *list) {
    if (!list) return;
    free(list->entries);
    free(list);
}

/* ────────────────────────────────────────────────────────────────────────────
 * File info
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * Get file/directory metadata. Returns 0 on success, -1 on error.
 */
int smb2w_stat(
    struct smb2_context *ctx,
    const char *path,
    uint32_t *out_type,
    uint64_t *out_size,
    uint64_t *out_mtime,
    uint64_t *out_btime
) {
    if (!ctx) return -1;

    struct smb2_stat_64 st;
    int rc = smb2_stat(ctx, path, &st);
    if (rc < 0) return -1;

    if (out_type)  *out_type  = st.smb2_type;
    if (out_size)  *out_size  = st.smb2_size;
    if (out_mtime) *out_mtime = st.smb2_mtime;
    if (out_btime) *out_btime = st.smb2_btime;
    return 0;
}

/*
 * Get file size without opening the file. Returns -1 on error.
 * Uses a compound request internally (Create + QueryInfo + Close).
 */
int64_t smb2w_filesize(struct smb2_context *ctx, const char *path) {
    if (!ctx) return -1;

    struct smb2_stat_64 st;
    if (smb2_stat(ctx, path, &st) < 0) return -1;
    return (int64_t)st.smb2_size;
}

/* ────────────────────────────────────────────────────────────────────────────
 * File writing
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * Write `length` bytes from `buf` to `path` at `offset`.
 * Opens the file with O_WRONLY|O_CREAT, writes in chunks, then closes.
 * Returns the number of bytes written, or -1 on error.
 */
int smb2w_pwrite(
    struct smb2_context *ctx,
    const char *path,
    const uint8_t *buf,
    uint32_t length,
    uint64_t offset
) {
    if (!ctx || !path || !buf) return -1;

    struct smb2fh *fh = smb2_open(ctx, path, O_WRONLY | O_CREAT);
    if (!fh) return -1;

    uint32_t max_chunk = smb2_get_max_write_size(ctx);
    if (max_chunk == 0) max_chunk = 1048576;

    uint32_t total = 0;
    while (total < length) {
        uint32_t chunk = length - total;
        if (chunk > max_chunk) chunk = max_chunk;
        int n = smb2_pwrite(ctx, fh, (uint8_t *)(buf + total), chunk, offset + total);
        if (n < 0) { smb2_close(ctx, fh); return -1; }
        if (n == 0) break; /* cannot make progress */
        total += (uint32_t)n;
    }

    smb2_close(ctx, fh);
    return (int)total;
}

/*
 * Write an entire buffer to a file, creating or truncating it.
 * Returns the number of bytes written, or -1 on error.
 */
int smb2w_write_file(
    struct smb2_context *ctx,
    const char *path,
    const uint8_t *buf,
    uint32_t length
) {
    if (!ctx || !path || !buf) return -1;

    struct smb2fh *fh = smb2_open(ctx, path, O_WRONLY | O_CREAT | O_TRUNC);
    if (!fh) return -1;

    uint32_t max_chunk = smb2_get_max_write_size(ctx);
    if (max_chunk == 0) max_chunk = 1048576;

    uint32_t total = 0;
    while (total < length) {
        uint32_t chunk = length - total;
        if (chunk > max_chunk) chunk = max_chunk;
        int n = smb2_pwrite(ctx, fh, (uint8_t *)(buf + total), chunk, (uint64_t)total);
        if (n < 0) { smb2_close(ctx, fh); return -1; }
        if (n == 0) break; /* cannot make progress */
        total += (uint32_t)n;
    }

    smb2_close(ctx, fh);
    return (int)total;
}

/*
 * Open a file for writing and return its handle.
 * Flags: O_WRONLY | O_CREAT (append/overwrite at chosen offset).
 * The caller MUST close the handle with smb2w_close_file().
 */
struct smb2fh *smb2w_open_file_write(struct smb2_context *ctx, const char *path) {
    if (!ctx || !path) return NULL;
    return smb2_open(ctx, path, O_WRONLY | O_CREAT);
}

/*
 * Write to an open file handle at `offset`.
 * Returns the number of bytes written, or -1 on error.
 */
int smb2w_pwrite_handle(
    struct smb2_context *ctx,
    struct smb2fh *fh,
    const uint8_t *buf,
    uint32_t length,
    uint64_t offset
) {
    if (!ctx || !fh || !buf) return -1;

    uint32_t max_chunk = smb2_get_max_write_size(ctx);
    if (max_chunk == 0) max_chunk = 1048576;

    uint32_t total = 0;
    while (total < length) {
        uint32_t chunk = length - total;
        if (chunk > max_chunk) chunk = max_chunk;
        int n = smb2_pwrite(ctx, fh, (uint8_t *)(buf + total), chunk, offset + total);
        if (n < 0) return -1;
        if (n == 0) break; /* cannot make progress */
        total += (uint32_t)n;
    }
    return (int)total;
}

/* ────────────────────────────────────────────────────────────────────────────
 * File/directory management
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * Delete a file. Returns 0 on success, -1 on error.
 */
int smb2w_unlink(struct smb2_context *ctx, const char *path) {
    if (!ctx || !path) return -1;
    return smb2_unlink(ctx, path);
}

/*
 * Create a directory. Returns 0 on success, -1 on error.
 */
int smb2w_mkdir(struct smb2_context *ctx, const char *path) {
    if (!ctx || !path) return -1;
    return smb2_mkdir(ctx, path);
}

/*
 * Delete a directory. Returns 0 on success, -1 on error.
 */
int smb2w_rmdir(struct smb2_context *ctx, const char *path) {
    if (!ctx || !path) return -1;
    return smb2_rmdir(ctx, path);
}

/*
 * Rename (move) a file or directory. Returns 0 on success, -1 on error.
 */
int smb2w_rename(struct smb2_context *ctx, const char *oldpath, const char *newpath) {
    if (!ctx || !oldpath || !newpath) return -1;
    return smb2_rename(ctx, oldpath, newpath);
}

/*
 * Truncate a file to `length` bytes. Returns 0 on success, -1 on error.
 */
int smb2w_truncate(struct smb2_context *ctx, const char *path, uint64_t length) {
    if (!ctx || !path) return -1;
    return smb2_truncate(ctx, path, length);
}

/*
 * Truncate an open file handle to `length` bytes.
 * Returns 0 on success, -1 on error.
 */
int smb2w_ftruncate(struct smb2_context *ctx, struct smb2fh *fh, uint64_t length) {
    if (!ctx || !fh) return -1;
    return smb2_ftruncate(ctx, fh, length);
}

/*
 * Flush an open file handle to disk.
 * Returns 0 on success, -1 on error.
 */
int smb2w_fsync(struct smb2_context *ctx, struct smb2fh *fh) {
    if (!ctx || !fh) return -1;
    return smb2_fsync(ctx, fh);
}

/*
 * Send a keepalive echo to the server.
 * Returns 0 on success, -1 on error.
 */
int smb2w_echo(struct smb2_context *ctx) {
    if (!ctx) return -1;
    return smb2_echo(ctx);
}

/*
 * Read the target of a symbolic link.
 * Copies the target path into `buf` (up to `bufsiz` bytes).
 * Returns 0 on success, -1 on error.
 */
int smb2w_readlink(struct smb2_context *ctx, const char *path,
                   char *buf, uint32_t bufsiz) {
    if (!ctx || !path || !buf || bufsiz == 0) return -1;
    return smb2_readlink(ctx, path, buf, bufsiz);
}

/* ────────────────────────────────────────────────────────────────────────────
 * Filesystem info
 * ──────────────────────────────────────────────────────────────────────────── */

/*
 * FFI-safe filesystem stats. Matches layout of smb2_statvfs but uses
 * fixed-width types for predictable struct packing across platforms.
 */
struct smb2w_statvfs {
    uint32_t f_bsize;     /* fundamental block size */
    uint32_t f_frsize;    /* fragment size */
    uint64_t f_blocks;    /* total data blocks */
    uint64_t f_bfree;     /* free blocks */
    uint64_t f_bavail;    /* available blocks for non-root */
    uint32_t f_files;     /* total file nodes */
    uint32_t f_ffree;     /* free file nodes */
    uint32_t f_favail;    /* free file nodes for non-root */
    uint32_t f_fsid;      /* filesystem ID */
    uint32_t f_flag;      /* mount flags */
    uint32_t f_namemax;   /* max filename length */
};

/*
 * Get filesystem statistics for a share.
 * Returns 0 on success, -1 on error.
 */
int smb2w_statvfs(struct smb2_context *ctx, const char *path,
                  struct smb2w_statvfs *out) {
    if (!ctx || !path || !out) return -1;

    struct smb2_statvfs st;
    int rc = smb2_statvfs(ctx, path, &st);
    if (rc < 0) return -1;

    out->f_bsize   = st.f_bsize;
    out->f_frsize  = st.f_frsize;
    out->f_blocks  = st.f_blocks;
    out->f_bfree   = st.f_bfree;
    out->f_bavail  = st.f_bavail;
    out->f_files   = st.f_files;
    out->f_ffree   = st.f_ffree;
    out->f_favail  = st.f_favail;
    out->f_fsid    = st.f_fsid;
    out->f_flag    = st.f_flag;
    out->f_namemax = st.f_namemax;
    return 0;
}
