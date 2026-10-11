# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Header hygiene for llvm-mingw: asprintf fallbacks + config.h in compat.c.

Two upstream assumptions break under the llvm-mingw toolchain we build with,
which is newer than the mingw runtimes upstream targets.

1. include/asprintf.h — asprintf/vasprintf redefinition
------------------------------------------------------
The fallback implementations are guarded with `#ifndef vasprintf` /
`#ifndef asprintf`. Those test for *macros*, but modern mingw-w64 declares
asprintf/vasprintf as real *functions* in <stdio.h>, so the guards never fire
and we end up with two conflicting definitions:

    asprintf.h:32:19: error: redefinition of 'vasprintf'
    stdio.h:276:5: note: previous definition is here

The same block also calls _vscprintf_so(), which upstream already declares
only `#if !defined(__MINGW32__)` — so under mingw the body referenced a
function that was never defined:

    asprintf.h:36:13: error: call to undeclared function '_vscprintf_so'

Upstream's own guard shows the intent: mingw supplies these itself. Extend
that same condition to the two fallbacks instead of inventing a new rule.

2. lib/compat.c — never includes config.h, so NEED_* is invisible
-----------------------------------------------------------------
compat.c guards its POSIX shims (random(), srandom(), getlogin_r(), ...)
behind NEED_RANDOM / NEED_SRANDOM / NEED_GETLOGIN_R, but — unlike every other
file in lib/ — it never performs the `#ifdef HAVE_CONFIG_H #include "config.h"`
dance. The switches defined in our config.h therefore never reach it and the
shims are compiled out, leaving lib/init.c unresolved at link time:

    ld.lld: error: undefined symbol: random
    >>> referenced by init.o:(smb2_random_bytes)
    ld.lld: error: undefined symbol: srandom
    ld.lld: error: undefined symbol: getlogin_r

Add the same preamble the rest of lib/ uses. compat.c tests no HAVE_* macros
at all, so pulling config.h in changes nothing beyond making the NEED_*
switches visible.

Touches: include/asprintf.h, lib/compat.c
"""
import sys
import os

root = sys.argv[1]


def patch(relpath, pairs):
    fn = os.path.join(root, relpath)
    with open(fn) as f:
        content = f.read()
    for old, new in pairs:
        if old not in content:
            print(f"ERROR: anchor not found in {relpath} (upstream drifted?):")
            print(old)
            sys.exit(1)
        content = content.replace(old, new, 1)
    with open(fn, "w") as f:
        f.write(content)


patch("include/asprintf.h", [
    (
        "#ifndef vasprintf\n"
        "static inline int vasprintf(char **strp, const char *fmt, va_list ap) {\n",

        "/* mingw-w64 declares vasprintf() in <stdio.h> as a function, so the\n"
        " * plain #ifndef below does not catch it — match the __MINGW32__ guard\n"
        " * already used for _vscprintf_so() above. */\n"
        "#if !defined(vasprintf) && !defined(__MINGW32__)\n"
        "static inline int vasprintf(char **strp, const char *fmt, va_list ap) {\n",
    ),
    (
        "#ifndef asprintf\n"
        "static inline int asprintf(char *strp[], const char *fmt, ...) {\n",

        "#if !defined(asprintf) && !defined(__MINGW32__)\n"
        "static inline int asprintf(char *strp[], const char *fmt, ...) {\n",
    ),
])

patch("lib/compat.c", [
    (
        "*/\n"
        "\n"
        "#include \"compat.h\"\n",

        "*/\n"
        "#ifdef HAVE_CONFIG_H\n"
        "#include \"config.h\"\n"
        "#endif\n"
        "\n"
        "#include \"compat.h\"\n",
    ),
])

print("Patched: asprintf/vasprintf mingw guards, "
      "config.h in compat.c (asprintf.h, compat.c)")
