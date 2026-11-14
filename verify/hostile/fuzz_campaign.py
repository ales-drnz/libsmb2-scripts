#!/usr/bin/env python3
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
"""A bounded, single-process mutation campaign: harness -> mutating proxy ->
a real SMB server. One client run per iteration, one after the other; the
mutations of iteration i depend only on (--seed, i).

    fuzz_campaign.py <harness> <dir on the share> <out_dir> [--iters 3000]
        [--seed S] [--upstream 127.0.0.1:445] [--share public] [--start 0]

Every iteration picks, from its own seed: the client operations, the
dialect, how many server frames to leave alone (the connect is covered by
the 3.1.1 preauth hash, so most runs start mutating after it), the
mutation rate, and whether the proxy closes an idle connection after 0.3 s
(most runs: keeps a stall from costing a whole timeout) or leaves a stall
to the library's own timeout (1 s).

Keeps a log for every iteration that ended in a sanitizer report, a crash
or a client still running at the wall clock, and writes campaign.json.
Replay one iteration with --start i --iters 1.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mutating_proxy import Proxy  # noqa: E402

OPS = ['dsorc', 'orwfc', 'orc', 'dk', 'sv', 'E', 'dsorwfycklvemniu', 'ok', 'Ed', 'owyc', 'mnius',
       'dddd', 'orrc', 'kkss']
VERS = [0, 0, 0x0210, 0x0210, 0x0302, 0x0300, 0x0202]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('harness')
    ap.add_argument('dir')
    ap.add_argument('out')
    ap.add_argument('--iters', type=int, default=3000)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--seed', default='r12')
    ap.add_argument('--upstream', default='127.0.0.1:445')
    ap.add_argument('--share', default='public')
    ap.add_argument('--wall', type=float, default=8.0)
    a = ap.parse_args()
    host, port = a.upstream.rsplit(':', 1)
    os.makedirs(os.path.join(a.out, 'findings'), exist_ok=True)
    proxy = Proxy(0, (host, int(port)), log=lambda s: None)
    env = dict(os.environ)
    env.pop('LD_PRELOAD', None)
    env['ASAN_OPTIONS'] = 'detect_leaks=1:exitcode=99'
    env['UBSAN_OPTIONS'] = 'print_stacktrace=1:halt_on_error=1'
    tally = {}
    kinds = {}
    findings = []
    t_start = time.monotonic()
    for i in range(a.start, a.start + a.iters):
        if i % 250 == 0:
            subprocess.run([a.harness, 'fixture-create', a.upstream, a.share, a.dir], env=env,
                           capture_output=True)
        rng = random.Random('%s/%d' % (a.seed, i))
        ops = rng.choice(OPS)
        ver = rng.choice(VERS)
        skip = rng.choice([0, 1, 2, 3, 4, 4, 4, 4, 5, 6, 8, 12])
        rate = rng.choice([0.1, 0.2, 0.3, 0.5, 1.0])
        idle = 0.0 if rng.random() < 0.15 else 0.3
        max_mut = rng.choice([1, 1, 2, 0])
        proxy.set_run('%s/%d' % (a.seed, i), skip, rate, idle, max_mut)
        cmd = [a.harness, '127.0.0.1:%d' % proxy.port, a.share, a.dir, ops, '1']
        if ver:
            cmd.append('0x%04x' % ver)
        t0 = time.monotonic()
        killed = False
        try:
            p = subprocess.run(cmd, env=env, capture_output=True, timeout=a.wall)
            out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            killed, out, err, rc = True, e.stdout or b'', e.stderr or b'', None
        dt = time.monotonic() - t0
        out = out.decode('utf-8', 'replace')
        err = err.decode('utf-8', 'replace')
        events = list(proxy.events)
        if 'AddressSanitizer' in err or 'runtime error:' in err:
            outcome = 'MEMORY'
        elif 'LeakSanitizer' in err:
            outcome = 'leak'
        elif killed:
            outcome = 'still-running-at-wall'
        elif rc != 0:
            outcome = 'CRASH'
        elif not [e for e in events if e != 'idle-close']:
            outcome = 'no-mutation'
        elif re.search(r'rc=-\d+', out.replace('unlink     rc=-2', '')) or 'NULL' in out:
            outcome = 'error-returned'
        else:
            outcome = 'accepted'
        tally[outcome] = tally.get(outcome, 0) + 1
        for e in events:
            k = e.split()[2] if len(e.split()) > 2 else e
            kinds[k] = kinds.get(k, 0) + 1
        if outcome in ('MEMORY', 'leak', 'CRASH', 'still-running-at-wall') or 'OVERRUN' in out:
            m = re.search(r'(ERROR: \w+Sanitizer: [^\n]*|[^\n]*runtime error: [^\n]*)', err)
            findings.append(dict(iter=i, outcome=outcome, ops=ops, ver=ver, skip=skip, rate=rate,
                                 idle=idle, max_mut=max_mut, events=events, seconds=round(dt, 2),
                                 summary=m.group(1) if m else ''))
            with open(os.path.join(a.out, 'findings', '%05d-%s.log' % (i, outcome)), 'w') as f:
                f.write('$ %s\n# seed=%s/%d skip=%d rate=%s idle=%s max_mut=%d rc=%s %.2fs\n'
                        '# events: %s\n--- stdout\n%s--- stderr\n%s'
                        % (' '.join(cmd), a.seed, i, skip, rate, idle, max_mut, rc, dt,
                           events, out, err))
        if (i + 1) % 100 == 0:
            print('%d iterations, %.0fs: %s' % (i + 1 - a.start, time.monotonic() - t_start,
                                                 tally), flush=True)
    summary = dict(seed=a.seed, start=a.start, iters=a.iters,
                   seconds=round(time.monotonic() - t_start), tally=tally, mutation_kinds=kinds,
                   findings=findings)
    with open(os.path.join(a.out, 'campaign.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    print('DONE', json.dumps(dict(tally=tally, kinds=kinds)))


if __name__ == '__main__':
    main()
