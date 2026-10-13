# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""Guard the global active_contexts list with a lock.

lib/init.c links every context into the process-wide `active_contexts`
list in smb2_init_context() and unlinks it in smb2_destroy_context(),
without any locking. dart_smb2 runs one context per worker isolate, and
isolates are OS threads: a pool that connects, reconnects or disconnects
several workers at once calls these two functions concurrently, and an
interleaved SMB2_LIST_ADD / SMB2_LIST_REMOVE corrupts the list.

Both mutations, and the walk in smb2_context_active() (exported, and
called from any thread that holds a context), now run under a static lock
(an SRWLOCK on Windows, a pthread mutex elsewhere). smb2_active_contexts()
hands out the head of the list for the server-side loops in
lib/libsmb2.c, which walk it after the call returns, so no lock inside it
could cover them; dart_smb2 never runs those loops, and it is left as is.

The script is BSD-3-Clause; the code it adds to libsmb2 is distributed
under libsmb2's LGPL-2.1-or-later.
"""
import os
import sys

root = sys.argv[1]
fn = os.path.join(root, "lib/init.c")
with open(fn) as f:
    content = f.read()

decl_old = "static struct smb2_context *active_contexts;\n"
decl_new = (
    "static struct smb2_context *active_contexts;\n"
    "\n"
    "/* dart_smb2: contexts are created and destroyed from several threads\n"
    " * (one per worker isolate), so the list mutations and\n"
    " * smb2_context_active() take a lock. */\n"
    "#ifdef _WIN32\n"
    "#include <windows.h>\n"
    "static SRWLOCK active_contexts_lock = SRWLOCK_INIT;\n"
    "#define ACTIVE_CONTEXTS_LOCK() AcquireSRWLockExclusive(&active_contexts_lock)\n"
    "#define ACTIVE_CONTEXTS_UNLOCK() ReleaseSRWLockExclusive(&active_contexts_lock)\n"
    "#else\n"
    "#include <pthread.h>\n"
    "static pthread_mutex_t active_contexts_lock = PTHREAD_MUTEX_INITIALIZER;\n"
    "#define ACTIVE_CONTEXTS_LOCK() pthread_mutex_lock(&active_contexts_lock)\n"
    "#define ACTIVE_CONTEXTS_UNLOCK() pthread_mutex_unlock(&active_contexts_lock)\n"
    "#endif\n"
)
add_old = "        SMB2_LIST_ADD(&active_contexts, smb2);\n"
add_new = (
    "        ACTIVE_CONTEXTS_LOCK();\n"
    "        SMB2_LIST_ADD(&active_contexts, smb2);\n"
    "        ACTIVE_CONTEXTS_UNLOCK();\n"
)
remove_old = "        SMB2_LIST_REMOVE(&active_contexts, smb2);\n"
remove_new = (
    "        ACTIVE_CONTEXTS_LOCK();\n"
    "        SMB2_LIST_REMOVE(&active_contexts, smb2);\n"
    "        ACTIVE_CONTEXTS_UNLOCK();\n"
)

active_old = (
    "        struct smb2_context *context = active_contexts;\n"
    "\n"
    "        while (context) {\n"
    "                if (smb2 == context) {\n"
    "                        return 1;\n"
    "                }\n"
    "                context = context->next;\n"
    "        }\n"
    "        return 0;\n"
)
active_new = (
    "        struct smb2_context *context;\n"
    "        int found = 0;\n"
    "\n"
    "        ACTIVE_CONTEXTS_LOCK();\n"
    "        for (context = active_contexts; context; context = context->next) {\n"
    "                if (smb2 == context) {\n"
    "                        found = 1;\n"
    "                        break;\n"
    "                }\n"
    "        }\n"
    "        ACTIVE_CONTEXTS_UNLOCK();\n"
    "        return found;\n"
)

for old in (decl_old, add_old, remove_old, active_old):
    if content.count(old) != 1:
        print(f"ERROR: anchor {old.strip()!r} not found exactly once in lib/init.c (upstream drifted?)")
        sys.exit(1)

content = content.replace(decl_old, decl_new, 1)
content = content.replace(add_old, add_new, 1)
content = content.replace(remove_old, remove_new, 1)
content = content.replace(active_old, active_new, 1)
with open(fn, "w") as f:
    f.write(content)
print("Patched lib/init.c: active_contexts list mutations and smb2_context_active() take a lock")
