# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Header hygiene for llvm-mingw: the asprintf fallbacks.

An upstream assumption breaks under the llvm-mingw toolchain we build
with, which is newer than the mingw runtimes upstream targets.

include/asprintf.h — asprintf/vasprintf redefinition
----------------------------------------------------
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

lib/compat.c used to need config.h for its NEED_* switches as well;
upstream includes it there since 8baba1f.

Touches: include/asprintf.h

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

p = Patch(sys.argv[1], sentinel=("include/asprintf.h", "!defined(vasprintf) && !defined(__MINGW32__)"))


def patch(relpath, pairs):
    for old, new in pairs:
        p.replace(relpath, old, new)


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

p.done("Patched: asprintf/vasprintf mingw guards (asprintf.h)")
