#!/usr/bin/env python3
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
"""Runs every case of hostile_server.py against a harness binary, one after
the other, and classifies what the client did.

    run_cases.py <harness> <out_dir> [--only REGEX] [--timeout 2]

Writes <out_dir>/results.json, <out_dir>/results.tsv and one log per case
in <out_dir>/logs/. Outcomes:
  clean-error   the library returned an error at once
  timeout       the library returned an error only after its timeout
  accepted      no error at all: the reply was taken as good
  not-reached   the case never fired (the client stopped earlier)
  unbounded     the client was still going when the wall clock ran out
  leak          LeakSanitizer only
  MEMORY        an AddressSanitizer / UBSan report
  CRASH         killed by a signal with no sanitizer report
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def run_case(harness, case, timeout, logdir):
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, 'hostile_server.py'),
                            '--port', '0', '--case', case['name']],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    port = int(srv.stdout.readline().split()[1])
    env = dict(os.environ)
    env.pop('LD_PRELOAD', None)
    env['ASAN_OPTIONS'] = 'detect_leaks=1:abort_on_error=0:exitcode=99'
    env['UBSAN_OPTIONS'] = 'print_stacktrace=1:halt_on_error=1'
    cmd = [harness, '127.0.0.1:%d' % port, 'public', 'dir', case['ops'], str(timeout)]
    if case.get('ver'):
        cmd.append('0x%04x' % case['ver'])
    wall = case.get('wall') or (3 * timeout + 4)
    t0 = time.monotonic()
    killed = False
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, timeout=wall)
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        killed = True
        out, err, rc = e.stdout or b'', e.stderr or b'', None
    dt = time.monotonic() - t0
    srv.terminate()
    sout, serr = srv.communicate()
    out = out.decode('utf-8', 'replace')
    err = err.decode('utf-8', 'replace')
    fired = 'FIRED' in sout or case['name'].startswith('none') or not case.get('cmd_set', True)
    errors = [l.strip() for l in out.splitlines()
              if re.search(r'rc=-\d+', l) and not l.strip().startswith('unlink')]
    if 'AddressSanitizer' in err or 'runtime error:' in err:
        outcome = 'MEMORY'
    elif 'LeakSanitizer' in err:
        outcome = 'leak'
    elif killed:
        outcome = 'unbounded'
    elif rc is not None and rc < 0:
        outcome = 'CRASH'
    elif rc not in (0,):
        outcome = 'CRASH'
    elif not fired:
        outcome = 'not-reached'
    elif errors:
        outcome = 'timeout' if dt >= timeout - 0.05 else 'clean-error'
    else:
        outcome = 'accepted'
    with open(os.path.join(logdir, case['name'] + '.log'), 'w') as f:
        f.write('$ %s\n# rc=%s wall=%.2fs outcome=%s\n--- stdout\n%s--- stderr\n%s--- server\n%s%s'
                % (' '.join(cmd), rc, dt, outcome, out, err, sout, serr))
    detail = errors[0] if errors else ''
    if 'OVERRUN-REPORTED' in out:
        detail = '[OVERRUN-REPORTED] ' + next(l.strip() for l in out.splitlines() if 'OVERRUN' in l)
    if outcome in ('MEMORY', 'leak'):
        m = re.search(r'(ERROR: \w+Sanitizer: [^\n]*|[^\n]*runtime error: [^\n]*)', err)
        detail = m.group(1) if m else detail
    return dict(name=case['name'], group=case['group'], desc=case['desc'], ops=case['ops'],
                ver=case.get('ver', 0), outcome=outcome, seconds=round(dt, 2), rc=rc,
                detail=detail[:300], fired=fired)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('harness')
    ap.add_argument('out')
    ap.add_argument('--only')
    ap.add_argument('--timeout', type=int, default=2)
    a = ap.parse_args()
    cases = json.loads(subprocess.check_output(
        [sys.executable, os.path.join(HERE, 'hostile_server.py'), '--list', '--json']))
    if a.only:
        cases = [c for c in cases if re.search(a.only, c['name'])]
    logdir = os.path.join(a.out, 'logs')
    os.makedirs(logdir, exist_ok=True)
    results = []
    for i, c in enumerate(cases):
        r = run_case(a.harness, c, a.timeout, logdir)
        results.append(r)
        print('%4d/%d %-12s %5.1fs %-46s %s' % (i + 1, len(cases), r['outcome'], r['seconds'],
                                                 r['name'], r['detail'][:110]), flush=True)
    with open(os.path.join(a.out, 'results.json'), 'w') as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(a.out, 'results.tsv'), 'w') as f:
        for r in results:
            f.write('\t'.join(str(r[k]) for k in ('name', 'group', 'outcome', 'seconds', 'detail',
                                                  'desc')) + '\n')
    tally = {}
    for r in results:
        tally[r['outcome']] = tally.get(r['outcome'], 0) + 1
    print('TOTAL %d: %s' % (len(results), tally))


if __name__ == '__main__':
    main()
