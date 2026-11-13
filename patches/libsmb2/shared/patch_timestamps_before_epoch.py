# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Give a timestamp before 1970 as 0 instead of a date far in the future.

smb2_win_to_timeval() in lib/timestamps.c subtracts the 1601-to-1970
offset from the FILETIME as an unsigned 64-bit number. A FILETIME below
that offset wraps: 0, which a server sends for a time it does not keep,
came out as tv_sec = 1833029933770 with a 64-bit time_t, some 58 thousand
years from now, in the times of stat, fstat and readdir.

A FILETIME before 1-1-1970 now gives tv_sec = 0 and tv_usec = 0, the
value smb2_tv_timeval_to_win() already writes back as FILETIME 0. Struct
smb2_timeval and smb2_stat_64 keep their layout.

Not changed: tv_sec is a time_t, so where time_t has 32 bits (Android
armeabi-v7a) a time after 19-1-2038 still does not fit.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

root = sys.argv[1]
fn = os.path.join(root, "lib/timestamps.c")
with open(fn) as f:
    content = f.read()

old = (
    "smb2_win_to_timeval(uint64_t smb2_time, struct smb2_timeval *tv)\n"
    "{\n"
    "        tv->tv_usec = (smb2_time / 10) % 1000000;\n"
    "        tv->tv_sec  = (smb2_time - 116444736000000000) / 10000000;\n"
    "}\n"
)
new = (
    "smb2_win_to_timeval(uint64_t smb2_time, struct smb2_timeval *tv)\n"
    "{\n"
    "        /* dart_smb2: a time before 1970, 0 above all, is 0 and does not\n"
    "         * wrap (see patch_timestamps_before_epoch.py). */\n"
    "        if (smb2_time < 116444736000000000ULL) {\n"
    "                tv->tv_sec = 0;\n"
    "                tv->tv_usec = 0;\n"
    "                return;\n"
    "        }\n"
    "        tv->tv_usec = (smb2_time / 10) % 1000000;\n"
    "        tv->tv_sec  = (smb2_time - 116444736000000000) / 10000000;\n"
    "}\n"
)

if content.count(old) != 1:
    print("ERROR: smb2_win_to_timeval anchor not found exactly once in lib/timestamps.c (upstream drifted?)")
    sys.exit(1)

with open(fn, "w") as f:
    f.write(content.replace(old, new, 1))
print("Patched lib/timestamps.c: a FILETIME before 1970 converts to 0")
