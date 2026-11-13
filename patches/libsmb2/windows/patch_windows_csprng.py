# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Give smb2_random_bytes() a real CSPRNG on Windows (CNG / BCryptGenRandom).

smb2_random_bytes() picks the first strong entropy source the platform
advertises and, failing all of them, falls back to the random() sequence
seeded in smb2_init_context() with `time(NULL) ^ getpid()`. Upstream offers
three optional sources:

    HAVE_ARC4RANDOM_BUF   macOS/iOS, Android
    HAVE_GETRANDOM        Linux
    HAVE_DEV_URANDOM      Linux

Windows advertises none of them, so every value that function is supposed to
protect — the NTLMv2 client challenge, the SMB 3.1.1 preauth salt and the
AES-CCM nonce — would come from rand() seeded with a low-entropy, largely
guessable value. A repeated or predicted CCM nonce under a given key breaks
both confidentiality and integrity of the sealed traffic, which is exactly
what the comment above that function warns about.

Windows does have a system CSPRNG: CNG's BCryptGenRandom(). Called with
BCRYPT_USE_SYSTEM_PREFERRED_RNG it needs no algorithm handle. Wire it in as
one more optional source, in the shape upstream already established — try it,
return 0 on success, otherwise fall through to the remaining sources and
ultimately the random() fallback, so behaviour is never worse than before.

The length is fed in ULONG-sized chunks: cbBuffer is a ULONG while len is a
size_t, and on Win64 a >4 GiB request would otherwise truncate.

Requires -lbcrypt at link time and HAVE_BCRYPT_GENRANDOM from config.h.

Touches: lib/init.c

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from _patchlib import Patch  # noqa: E402

p = Patch(sys.argv[1], sentinel=("lib/init.c", "HAVE_BCRYPT_GENRANDOM"))


def patch(relpath, pairs):
    for old, new in pairs:
        p.replace(relpath, old, new)


patch("lib/init.c", [
    # 1. <bcrypt.h> — after compat.h, which is what drags in <windows.h>.
    (
        '#include "compat.h"\n'
        "\n"
        '#include "smb2.h"\n',

        '#include "compat.h"\n'
        "\n"
        "#ifdef HAVE_BCRYPT_GENRANDOM\n"
        "#include <bcrypt.h>\n"
        "#endif\n"
        "\n"
        '#include "smb2.h"\n',
    ),
    # 2. The CNG source itself, ahead of the POSIX ones.
    (
        "#else /* !HAVE_ARC4RANDOM_BUF */\n"
        "\n"
        "#ifdef HAVE_GETRANDOM\n",

        "#else /* !HAVE_ARC4RANDOM_BUF */\n"
        "\n"
        "#ifdef HAVE_BCRYPT_GENRANDOM\n"
        "        {\n"
        "                size_t done = 0;\n"
        "\n"
        "                while (done < len) {\n"
        "                        size_t left = len - done;\n"
        "                        ULONG chunk = (left > 0x40000000)\n"
        "                                ? 0x40000000 : (ULONG)left;\n"
        "\n"
        "                        /* NULL algorithm handle is allowed with\n"
        "                         * BCRYPT_USE_SYSTEM_PREFERRED_RNG. */\n"
        "                        if (BCryptGenRandom(NULL, (PUCHAR)(p + done),\n"
        "                                            chunk,\n"
        "                                            BCRYPT_USE_SYSTEM_PREFERRED_RNG)\n"
        "                            < 0) {\n"
        "                                break;\n"
        "                        }\n"
        "                        done += chunk;\n"
        "                }\n"
        "                if (done == len) {\n"
        "                        return 0;\n"
        "                }\n"
        "        }\n"
        "#endif /* HAVE_BCRYPT_GENRANDOM */\n"
        "\n"
        "#ifdef HAVE_GETRANDOM\n",
    ),
])

p.done("Patched: BCryptGenRandom CSPRNG source in smb2_random_bytes (init.c)")
