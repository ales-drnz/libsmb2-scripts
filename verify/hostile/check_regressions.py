#!/usr/bin/env python3
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
"""Runs the cases of regressions.tsv against a harness and fails when one
of them ends the way the patch it names stops: a sanitizer report, a
crash, or a client that never returns.

    check_regressions.py <harness> <out_dir>

regressions.tsv has one line per patch: the patch, and a regular
expression of the cases of hostile_cases.py it answers for. Build the
harness with build_asan.sh; <out_dir> is outside the repository.
"""
import csv
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BAD = {'MEMORY', 'CRASH', 'unbounded', 'leak'}


def main():
    harness, out = sys.argv[1], sys.argv[2]
    rules = [line.rstrip('\n').split('\t')
             for line in open(os.path.join(HERE, 'regressions.tsv'))
             if line.strip() and not line.startswith('#')]
    only = '|'.join('(?:%s)' % rx for _, rx in rules)
    subprocess.run([sys.executable, os.path.join(HERE, 'run_cases.py'),
                    harness, out, '--only', only],
                   stdout=subprocess.DEVNULL, check=True)
    results = {r[0]: r[2] for r in csv.reader(
        open(os.path.join(out, 'results.tsv')), delimiter='\t') if len(r) > 2}
    failed = 0
    for patch, rx in rules:
        cases = [c for c in results if re.search(rx, c)]
        bad = [c for c in cases if results[c] in BAD]
        print('%-36s %3d cases, %d failed' % (patch, len(cases), len(bad)))
        for c in bad:
            print('    %s: %s' % (c, results[c]))
        if not cases:
            print('    no case matches %s' % rx)
        failed += len(bad) + (not cases)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
