#!/usr/bin/env python3
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
"""A mutating TCP proxy between an SMB2 client and a real server.

Client -> server bytes are forwarded untouched. Server -> client data is
reassembled into NetBIOS session frames and each frame may be mutated,
deterministically from (seed, frame index): bit flips, overwrites of 16/32
bit fields with boundary values, edits of the NetBIOS length, truncation
(with or without closing the connection), duplicated or dropped frames.

Used as a library by fuzz_campaign.py (one seed per client run), or alone:

    mutating_proxy.py --listen 4455 --upstream 127.0.0.1:445 --seed 7 \
        [--skip 4] [--rate 0.3] [--dump]

--skip N leaves the first N server frames alone (negotiate and session
setup are covered by the preauth hash / signature on SMB 3.1.1, so a
mutation there only ever yields "wrong signature"). --dump prints one line
per frame in both directions (commands, status, sizes) and mutates nothing
unless --seed is given.
"""
import argparse
import random
import select
import socket
import struct
import threading
import time

CMD = ['NEGOTIATE', 'SESSION_SETUP', 'LOGOFF', 'TREE_CONNECT', 'TREE_DISCONNECT',
       'CREATE', 'CLOSE', 'FLUSH', 'READ', 'WRITE', 'LOCK', 'IOCTL', 'CANCEL',
       'ECHO', 'QUERY_DIRECTORY', 'CHANGE_NOTIFY', 'QUERY_INFO', 'SET_INFO',
       'OPLOCK_BREAK']

INTERESTING32 = [0, 1, 0x7f, 0x80, 0xff, 0x100, 0xffff, 0x10000, 0x7fffffff,
                 0x80000000, 0xfffffffe, 0xffffffff, 0x00ffffff, 0x01000000]
INTERESTING16 = [0, 1, 0x7f, 0x80, 0xff, 0x100, 0x7fff, 0x8000, 0xfffe, 0xffff]


def describe(frame):
    """One line for a NetBIOS frame: the commands of its compound chain."""
    out = []
    off = 4
    while off + 64 <= len(frame):
        magic = frame[off:off + 4]
        if magic == b'\xfdSMB':
            out.append('TRANSFORM')
            break
        if magic != b'\xfeSMB':
            out.append('?%s' % magic.hex())
            break
        status, cmd, credits, flags, nxt, mid = struct.unpack_from('<IHHIIQ', frame, off + 8)
        name = CMD[cmd] if cmd < len(CMD) else str(cmd)
        out.append('%s(mid=%d st=%08x cr=%d)' % (name, mid, status, credits))
        if nxt == 0:
            break
        off += nxt
    return '%5d %s' % (len(frame) - 4, ' + '.join(out))


def mutate(frame, rng):
    """Returns (list of byte strings to send, close_after, description)."""
    data = bytearray(frame)
    n = len(data)
    kind = rng.choices(
        ['bitflip', 'field32', 'field16', 'byte', 'nbsize', 'trunc_close',
         'trunc_fix', 'trunc_hang', 'dup', 'drop', 'multi', 'hdrfield'],
        [18, 22, 14, 8, 5, 5, 6, 2, 3, 2, 10, 10])[0]
    desc = kind
    if kind == 'bitflip':
        k = rng.randint(1, 4)
        for _ in range(k):
            pos = rng.randrange(4, n)
            data[pos] ^= 1 << rng.randrange(8)
            desc += ' @%d' % pos
    elif kind == 'field32' and n >= 8 + 64:
        # body fields are 2/4 byte aligned: favour the reply body
        pos = 4 + 64 + 2 * rng.randrange(0, max(1, (n - 68 - 4) // 2 + 1))
        pos = min(pos, n - 4)
        if rng.random() < 0.5:
            val = rng.choice(INTERESTING32)
        else:
            old = struct.unpack_from('<I', data, pos)[0]
            val = (old + rng.choice([-64, -8, -4, -2, -1, 1, 2, 4, 8, 64, 0x1000, n, n - 68])) & 0xffffffff
        struct.pack_into('<I', data, pos, val)
        desc += ' @%d=%#x' % (pos, val)
    elif kind == 'field16' and n >= 8 + 64:
        pos = 4 + 64 + 2 * rng.randrange(0, max(1, (n - 68 - 2) // 2 + 1))
        pos = min(pos, n - 2)
        if rng.random() < 0.5:
            val = rng.choice(INTERESTING16)
        else:
            old = struct.unpack_from('<H', data, pos)[0]
            val = (old + rng.choice([-64, -8, -2, -1, 1, 2, 8, 64, n & 0xffff])) & 0xffff
        struct.pack_into('<H', data, pos, val)
        desc += ' @%d=%#x' % (pos, val)
    elif kind == 'byte':
        pos = rng.randrange(4, n)
        data[pos] = rng.choice([0, 1, 0x7f, 0x80, 0xff, rng.randrange(256)])
        desc += ' @%d=%#x' % (pos, data[pos])
    elif kind == 'nbsize':
        val = rng.choice([0, 1, 63, 64, 65, n - 5, n - 3, n + 60, 0xffff,
                          0x00ffffff, 0x01000000, 0x01000001, 0x7fffffff,
                          0xffffffff, rng.randrange(0, 2 * n)])
        struct.pack_into('>I', data, 0, val & 0xffffffff)
        desc += ' =%#x' % val
    elif kind == 'trunc_close':
        cut = rng.randrange(1, n)
        return [bytes(data[:cut])], True, '%s @%d/%d' % (kind, cut, n)
    elif kind == 'trunc_fix' and n > 8:
        # shorter frame with a NetBIOS length that matches what is sent
        cut = rng.randrange(5, n)
        data = data[:cut]
        struct.pack_into('>I', data, 0, cut - 4)
        desc += ' @%d/%d' % (cut, n)
    elif kind == 'trunc_hang':
        cut = rng.randrange(1, n)
        return [bytes(data[:cut])], False, '%s @%d/%d' % (kind, cut, n)
    elif kind == 'dup':
        return [bytes(data), bytes(data)], False, kind
    elif kind == 'drop':
        return [], False, kind
    elif kind == 'hdrfield' and n >= 68:
        # SMB2 header: StructureSize, CreditCharge, Status, Command, Credits,
        # Flags, NextCommand, MessageId, TreeId, SessionId
        name, off, size = rng.choice([('magic', 0, 4), ('hdrsize', 4, 2), ('status', 8, 4),
                                      ('command', 12, 2), ('credits', 14, 2), ('flags', 16, 4),
                                      ('next', 20, 4), ('mid', 24, 8), ('tree', 36, 4),
                                      ('session', 40, 8)])
        if name == 'status':
            val = rng.choice([0, 0x103, 0xc0000016, 0x80000005, 0x8000002d, 0xc0000011,
                              0xc000000d, 0xc0000022, 0x80000006, 0x0000010c, 0xc0000203])
        elif name == 'next':
            val = rng.choice([0, 8, 64, 72, n - 4, n, n + 8, 0xffffffff, 0x80000000,
                              rng.randrange(0, n) & ~7])
        elif name == 'command':
            val = rng.randrange(0, 20)
        elif name == 'flags':
            val = struct.unpack_from('<I', data, 4 + off)[0] ^ (1 << rng.choice([0, 1, 2, 3, 4, 28, 29]))
        else:
            val = rng.choice([0, 1, 0xffff, rng.getrandbits(8 * size)])
        data[4 + off:4 + off + size] = (val & ((1 << (8 * size)) - 1)).to_bytes(size, 'little')
        desc += ' %s=%#x' % (name, val)
    else:  # multi, and the fallbacks of frames too short for a field edit
        desc = 'multi'
        for _ in range(rng.randint(2, 12)):
            pos = rng.randrange(4, n)
            data[pos] = rng.randrange(256)
    return [bytes(data)], False, desc


class Proxy:
    """One listening socket; every accepted connection is relayed to the
    upstream with its own frame counter. The seed and the knobs can be
    changed between client runs (set_run)."""

    def __init__(self, listen_port, upstream, dump=False, log=None):
        self.upstream = upstream
        self.dump = dump
        self.log = log or (lambda s: print(s, flush=True))
        self.seed = None
        self.skip = 0
        self.rate = 0.3
        self.idle_close = 0.0
        self.max_mut = 0
        self.events = []
        self.lsock = socket.socket()
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind(('127.0.0.1', listen_port))
        self.lsock.listen(16)
        self.port = self.lsock.getsockname()[1]
        self.conn_no = 0
        threading.Thread(target=self._accept, daemon=True).start()

    def set_run(self, seed, skip=0, rate=0.3, idle_close=0.0, max_mut=0):
        self.seed, self.skip, self.rate = seed, skip, rate
        self.idle_close, self.max_mut = idle_close, max_mut
        self.events = []
        self.conn_no = 0

    def _accept(self):
        while True:
            try:
                c, _ = self.lsock.accept()
            except OSError:
                return
            no = self.conn_no
            self.conn_no += 1
            threading.Thread(target=self._relay, args=(c, no, self.seed, self.skip,
                                                       self.rate, self.idle_close,
                                                       self.max_mut, self.events),
                             daemon=True).start()

    def _relay(self, c, conn_no, seed, skip, rate, idle_close, max_mut, events):
        try:
            s = socket.create_connection(self.upstream)
        except OSError as e:
            self.log('upstream: %s' % e)
            c.close()
            return
        for x in (c, s):
            x.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sbuf = b''
        cbuf = b''
        frame_no = 0
        muts = 0
        last = time.monotonic()
        try:
            while True:
                r, _, _ = select.select([c, s], [], [], 0.05)
                if not r:
                    if idle_close and time.monotonic() - last > idle_close:
                        events.append('idle-close')
                        break
                    continue
                last = time.monotonic()
                if c in r:
                    d = c.recv(1 << 20)
                    if not d:
                        break
                    s.sendall(d)
                    if self.dump:
                        cbuf += d
                        while len(cbuf) >= 4:
                            ln = struct.unpack('>I', cbuf[:4])[0] & 0xffffff
                            if len(cbuf) < 4 + ln:
                                break
                            self.log('C>S ' + describe(cbuf[:4 + ln]))
                            cbuf = cbuf[4 + ln:]
                if s in r:
                    d = s.recv(1 << 20)
                    if not d:
                        break
                    sbuf += d
                    close = False
                    while len(sbuf) >= 4 and not close:
                        ln = struct.unpack('>I', sbuf[:4])[0] & 0xffffff
                        if len(sbuf) < 4 + ln:
                            break
                        frame, sbuf = sbuf[:4 + ln], sbuf[4 + ln:]
                        if self.dump:
                            self.log('S>C ' + describe(frame))
                        out = [frame]
                        if seed is not None and frame_no >= skip and \
                                (not max_mut or muts < max_mut):
                            rng = random.Random('%s/%d/%d' % (seed, conn_no, frame_no))
                            if rng.random() < rate:
                                out, close, desc = mutate(frame, rng)
                                muts += 1
                                events.append('c%d f%d %s' % (conn_no, frame_no, desc))
                                if self.dump:
                                    self.log('    MUT ' + desc)
                        frame_no += 1
                        for o in out:
                            c.sendall(o)
                    if close:
                        break
        except OSError:
            pass
        finally:
            c.close()
            s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--listen', type=int, default=4455)
    ap.add_argument('--upstream', default='127.0.0.1:445')
    ap.add_argument('--seed')
    ap.add_argument('--skip', type=int, default=0)
    ap.add_argument('--rate', type=float, default=0.3)
    ap.add_argument('--idle-close', type=float, default=0.0)
    ap.add_argument('--dump', action='store_true')
    a = ap.parse_args()
    host, port = a.upstream.rsplit(':', 1)
    p = Proxy(a.listen, (host, int(port)), dump=a.dump)
    p.set_run(a.seed, a.skip, a.rate, a.idle_close)
    print('listening on 127.0.0.1:%d' % p.port, flush=True)
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
