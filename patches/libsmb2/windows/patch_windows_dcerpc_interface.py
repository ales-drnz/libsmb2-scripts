# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Rename struct dcerpc_service::interface — `interface` is reserved on Windows.

mingw's <rpc.h> (pulled in transitively via <windows.h>) contains:

    #define interface struct

a MIDL/COM heritage macro. It rewrites the member declaration in
include/dcerpc/dcerpc.h to `p_syntax_id_t *struct;`, so every translation
unit that reaches dcerpc.h after a Windows header fails to compile:

    dcerpc.h:128:24: error: expected member name or ';' after declaration
                            specifiers
      128 |         p_syntax_id_t *interface;
    rpc.h:12:19: note: expanded from macro 'interface'

Upstream never hits this because it does not build libdcerpc on Windows at
all (its symbols clash with Microsoft's own RPC runtime). We *do* build the
minimal NetrShareEnum path — lib/libsmb2-dcerpc*.c #include the libdcerpc
sources behind lib/libsmb2-dcerpc-prefix.h, which renames the symbols out of
the way — so the collision reaches us.

`#undef interface` is the popular workaround but the wrong one here: the
mingw-w64 maintainers decline to drop the macro because `interface` is a
reserved keyword in Windows/COM, and explicitly advise downstream projects to
stop using it as an identifier in public headers instead. Undefining it in a
public header would also silently break any later COM/RPC header in the same
translation unit.

So rename the member to `iface`, matching the name upstream already uses for
the same concept elsewhere (see include/dcerpc/dcerpc-epm.h). Struct layout —
and therefore ABI — is unchanged. The member is set only through positional
initializers in libdcerpc/dcerpc.c (`{"srvsvc", &srvsvc_interface, ...}`),
which need no edit, and is read in exactly one place: examples/dcerpc.c, which
is not built here but is fixed up so the patched tree stays self-consistent.

Windows-only: non-Windows trees keep upstream's spelling byte-for-byte.

Touches: include/dcerpc/dcerpc.h, examples/dcerpc.c
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


patch("include/dcerpc/dcerpc.h", [
    (
        "struct dcerpc_service {\n"
        "        const char *name;\n"
        "        p_syntax_id_t *interface;\n",

        "struct dcerpc_service {\n"
        "        const char *name;\n"
        "        /* Named `iface`, not `interface`: mingw's <rpc.h> defines\n"
        "         * `interface` as a macro expanding to `struct`. */\n"
        "        p_syntax_id_t *iface;\n",
    ),
])

patch("examples/dcerpc.c", [
    (
        "dcerpc_connect_context_async(dce, url->path, service->interface,",
        "dcerpc_connect_context_async(dce, url->path, service->iface,",
    ),
])

print("Patched: struct dcerpc_service::interface -> ::iface (dcerpc.h, examples/dcerpc.c)")
