/*
 * Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
 * All rights reserved.
 * Use of this source code is governed by BSD 3-Clause license that can be
 * found in the LICENSE file.
 *
 * dlopen_test <library> <symbols.txt> <release>
 *
 * Loads the library the way dart_smb2 does (RTLD_NOW | RTLD_LOCAL), resolves
 * every symbol listed in symbols.txt (one per line; blank lines and lines
 * starting with '#' are skipped), checks that smb2_scripts_release() returns
 * <release> (LIBSMB2_RELEASE, e.g. "r11"), then creates and destroys a
 * libsmb2 context, which runs libsmb2's initialisation (login name, random
 * seed) on this platform's libc. Exits non-zero on any failure.
 */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 4) {
        fprintf(stderr, "usage: %s <library> <symbols.txt> <release>\n", argv[0]);
        return 2;
    }

    void *h = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!h) {
        fprintf(stderr, "FAIL dlopen: %s\n", dlerror());
        return 1;
    }

    FILE *list = fopen(argv[2], "r");
    if (!list) {
        perror(argv[2]);
        return 2;
    }

    char line[256];
    int checked = 0, missing = 0;
    while (fgets(line, sizeof(line), list)) {
        line[strcspn(line, "\r\n")] = '\0';
        if (line[0] == '\0' || line[0] == '#') {
            continue;
        }
        checked++;
        if (!dlsym(h, line)) {
            fprintf(stderr, "FAIL missing symbol: %s\n", line);
            missing++;
        }
    }
    fclose(list);

    if (!missing) {
        const char *(*release)(void) =
            (const char *(*)(void))dlsym(h, "smb2_scripts_release");
        const char *got = release();
        if (!got || strcmp(got, argv[3]) != 0) {
            fprintf(stderr, "FAIL smb2_scripts_release returned \"%s\", expected \"%s\"\n",
                    got ? got : "(null)", argv[3]);
            missing++;
        }
    }

    if (!missing) {
        void *(*init)(void) = (void *(*)(void))dlsym(h, "smb2_init_context");
        void (*destroy)(void *) = (void (*)(void *))dlsym(h, "smb2_destroy_context");
        void *ctx = init();
        if (!ctx) {
            fprintf(stderr, "FAIL smb2_init_context returned NULL\n");
            missing++;
        } else {
            destroy(ctx);
        }
    }
    dlclose(h);

    if (missing) {
        fprintf(stderr, "FAIL %s: %d problem(s)\n", argv[1], missing);
        return 1;
    }
    printf("OK   %s: loaded, %d symbols resolved, release %s, context created and destroyed\n",
           argv[1], checked, argv[3]);
    return 0;
}
