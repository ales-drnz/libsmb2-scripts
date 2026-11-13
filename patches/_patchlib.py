# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

"""What every patches/libsmb2/<scope>/patch_*.py edits the libsmb2 tree with.

Not a patch itself: it lives one directory above the scopes and its name
does not start with patch_, so the build (scripts/shared/_helpers.sh), the
manifest (scripts/write_manifest.sh) and the TUI's Patches tab
(tui/catalog_patches.go), which all look for <scope>/patch_*.py, leave it
alone.

A patch script makes one Patch, calls its edits and ends with done():

    p = Patch(sys.argv[1], sentinel=("lib/sync.c", "prc = poll("))
    p.replace("lib/sync.c", old, new)
    p.done("Patched lib/sync.c: ...")

Three rules hold for every patch that way:

  - All or nothing. The edits are made on copies in memory, and done()
    writes the files only once every one of them matched. An anchor that
    drifted stops the script with exit status 1 and the tree as it was.

  - Anchors are counted. replace() wants its anchor exactly `count` times
    (once unless told otherwise) and replaces every one of them, so an
    anchor that upstream now has once more, or once less, is an error and
    not a silent edit of the wrong place.

  - A second run does nothing. The sentinel is a file and a text the patch
    puts in it, that upstream does not have and that no other patch adds
    or removes. When it is already there the patch has been applied: the
    script says so and exits 0 without touching the tree. done() refuses a
    sentinel its own edits did not put there, and writes the sentinel's
    file last, so a run that was interrupted between two files does not
    count as applied.

The builds always patch a tree they have just extracted, where "already
applied" can only mean that upstream now has the sentinel's text (after a
bump of the pin) or that another patch added it. They set
LIBSMB2_PATCH_FRESH=1, which makes it an error instead of a skip.
"""
import os
import sys


class Patch:
    """The edits of one patch script on the tree at `root`."""

    def __init__(self, root, sentinel, exit_if_applied=True):
        self.root = root
        self.name = os.path.basename(sys.argv[0])
        self.sentinel_path, self.sentinel_text = sentinel
        # relpath -> content, in the order the files were first touched.
        self.files = {}
        # relpath -> content in the tree; a file the patch creates is not here.
        self.original = {}
        self.applied = self.sentinel_text in self._load(self.sentinel_path)
        if self.applied and exit_if_applied:
            self.exit_applied()

    # ── Reading ──────────────────────────────────────────────────────────────

    def _load(self, relpath):
        if relpath not in self.files:
            try:
                with open(os.path.join(self.root, relpath)) as f:
                    self.original[relpath] = self.files[relpath] = f.read()
            except OSError as e:
                self.fail(f"cannot read {relpath}: {e.strerror}")
        return self.files[relpath]

    def text(self, relpath):
        """The file as the edits made so far leave it."""
        return self._load(relpath)

    def on_disk(self, relpath):
        """The file as it is in the tree, or None when it is not there."""
        try:
            with open(os.path.join(self.root, relpath)) as f:
                return f.read()
        except FileNotFoundError:
            return None

    # ── Edits (in memory) ────────────────────────────────────────────────────

    def replace(self, relpath, old, new, count=1):
        """Replace `old`, found exactly `count` times, with `new`."""
        content = self._load(relpath)
        found = content.count(old)
        if found != count:
            self.fail(
                f"anchor found {found} time(s) instead of {count} in {relpath} "
                "(upstream drifted?):\n" + old
            )
        self.files[relpath] = content.replace(old, new)

    def insert_at(self, relpath, offset, text):
        """Insert `text` at `offset` of text(relpath), for an anchor that
        replace() cannot express; the script finds and checks the place."""
        content = self._load(relpath)
        self.files[relpath] = content[:offset] + text + content[offset:]

    def append(self, relpath, text):
        """Add `text` at the end of the file."""
        self.files[relpath] = self._load(relpath) + text

    def require(self, relpath, text):
        """Stop unless the file has `text`: something an edit relies on
        without anchoring on it."""
        if text not in self._load(relpath):
            self.fail(f"{relpath} no longer has {text} (upstream drifted?)")

    def create(self, relpath, content):
        """A new file, which must not be in the tree yet."""
        if relpath in self.files or os.path.exists(os.path.join(self.root, relpath)):
            self.fail(f"{relpath} already exists (upstream drifted?)")
        self.files[relpath] = content

    # ── Endings ──────────────────────────────────────────────────────────────

    def fail(self, message):
        """Exit 1 with the tree as it was."""
        print(f"ERROR: {self.name}: {message}")
        sys.exit(1)

    def exit_applied(self):
        """Exit 0 with the tree as it was: the sentinel is already there."""
        if os.environ.get("LIBSMB2_PATCH_FRESH") == "1":
            self.fail(
                f"{self.sentinel_path} already has the patch's sentinel "
                f"{self.sentinel_text!r} before the patch ran (now upstream, "
                "or added by another patch?)"
            )
        print(f"Already applied: {self.name}")
        sys.exit(0)

    def done(self, message):
        """Write every file the edits changed, the sentinel's last, and
        report."""
        if self.sentinel_text not in self._load(self.sentinel_path):
            self.fail(
                f"the edits do not put the sentinel {self.sentinel_text!r} "
                f"in {self.sentinel_path}"
            )
        order = [p for p in self.files if p != self.sentinel_path]
        order.append(self.sentinel_path)
        for relpath in order:
            if self.files[relpath] == self.original.get(relpath):
                continue
            with open(os.path.join(self.root, relpath), "w") as f:
                f.write(self.files[relpath])
        print(message)
