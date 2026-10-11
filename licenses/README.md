# Third-party licences

The binaries this repository builds are libsmb2, compiled from the upstream
commit pinned in `scripts/shared/_versions.sh` with the patches in `patches/`
applied. libsmb2's `lib/` and `include/` are licensed under the GNU Lesser
General Public License, version 2.1 or later:

- [`libsmb2/COPYING`](libsmb2/COPYING): upstream's licence statement, copied
  from the pinned tarball.
- [`libsmb2/LICENCE-LGPL-2.1.txt`](libsmb2/LICENCE-LGPL-2.1.txt): the LGPL-2.1
  text.

The code the patch scripts add to libsmb2 is distributed under the same
LGPL-2.1-or-later terms. The scripts themselves, the build tooling and the TUI
are BSD-3-Clause ([`../LICENSE`](../LICENSE)).

Each `libsmb2-rN` release names in its `manifest.json` the libsmb2-scripts
commit it was built from: that commit, with the upstream tarball it pins, is
the corresponding source of the release's binaries.
