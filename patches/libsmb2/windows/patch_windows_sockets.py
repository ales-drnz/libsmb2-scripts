# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Win64 socket-handle correctness + Winsock header hygiene.

On Win64 a SOCKET is a 64-bit handle. connect_async_ai() returns the new
socket through an `int *fd_out`, which truncates real handle values
(Winsock handles are opaque and can exceed INT_MAX); it is widened to
t_socket. The `int maxfd` of the server loop in smb2_serve_port() stays as
upstream has it: Winsock's select() ignores its first argument, and the
server's extra_fdset hook takes an `int *`.

Also:

  - struct linger: mingw's <winsock2.h> already defines it; upstream's
    !HAVE_LINGER fallback redefinition collides — scope it to !_WIN32.
  - libsmb2.h pulls in <windows.h>: define WIN32_LEAN_AND_MEAN first so
    consumers don't drag the whole Win32 API (and its macro pollution) in.

Touches: lib/socket.c, include/smb2/libsmb2.h

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
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


patch("lib/socket.c", [
    (
        "#if !defined(HAVE_LINGER)\n",
        "#if !defined(HAVE_LINGER) && !defined(_WIN32)\n",
    ),
    (
        "connect_async_ai(struct smb2_context *smb2, const struct addrinfo *ai, int *fd_out)\n",
        "connect_async_ai(struct smb2_context *smb2, const struct addrinfo *ai, t_socket *fd_out)\n",
    ),
    (
        "        *fd_out = (int)fd;\n",
        "        *fd_out = fd;\n",
    ),
    (
        "                int fd;\n"
        "                err = connect_async_ai(smb2, ai, &fd);\n",
        "                t_socket fd;\n"
        "                err = connect_async_ai(smb2, ai, &fd);\n",
    ),
])


patch("include/smb2/libsmb2.h", [
    (
        "#if defined(_WINDOWS)\n",
        "#if defined(_WINDOWS)\n"
        "#ifndef WIN32_LEAN_AND_MEAN\n"
        "#define WIN32_LEAN_AND_MEAN\n"
        "#endif\n",
    ),
])

print("Patched: t_socket handle widths + Winsock header hygiene (socket.c, libsmb2.h)")
