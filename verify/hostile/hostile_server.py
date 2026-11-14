#!/usr/bin/env python3
# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
"""A hostile fake SMB2 server (Python 3, standard library only).

It speaks enough SMB2 to take a client through NEGOTIATE, SESSION_SETUP
(an NTLMSSP challenge; any credentials are accepted, nothing is signed) and
TREE_CONNECT, serves one directory with one file and one symbolic link, a
srvsvc pipe for share enumeration, and answers ONE chosen request with a
malformed reply. One case per run:

    hostile_server.py --list
    hostile_server.py --port 4460 --case read_datalen_gt_asked
    hostile_server.py --port 4460 --case none      # a well-behaved server

Every case names the client operations that reach it (`ops`, the letters of
the C harness; see cases.json written by --list --json) and the dialect the
server picks. The server prints the port it listens on, then one line when
the case fired ("FIRED").
"""
import argparse
import json
import socket
import struct
import sys
import threading
import time

(NEGOTIATE, SESSION_SETUP, LOGOFF, TREE_CONNECT, TREE_DISCONNECT, CREATE, CLOSE,
 FLUSH, READ, WRITE, LOCK, IOCTL, CANCEL, ECHO, QUERY_DIRECTORY, CHANGE_NOTIFY,
 QUERY_INFO, SET_INFO, OPLOCK_BREAK) = range(19)
CMDNAME = ['negotiate', 'session_setup', 'logoff', 'tree_connect', 'tree_disconnect',
           'create', 'close', 'flush', 'read', 'write', 'lock', 'ioctl', 'cancel',
           'echo', 'query_directory', 'change_notify', 'query_info', 'set_info',
           'oplock_break']

ST_OK = 0
ST_PENDING = 0x00000103
ST_MORE = 0xC0000016
ST_NO_MORE_FILES = 0x80000006
ST_EOF = 0xC0000011
ST_BUFFER_OVERFLOW = 0x80000005
ST_STOPPED_ON_SYMLINK = 0x8000002D
ST_NOT_SUPPORTED = 0xC00000BB
ST_ACCESS_DENIED = 0xC0000022
ST_INVALID_PARAMETER = 0xC000000D

FLAG_REPLY = 1
FLAG_ASYNC = 2
FLAG_RELATED = 4
FLAG_SIGNED = 8

FSCTL_GET_REPARSE_POINT = 0x000900A8
FSCTL_PIPE_TRANSCEIVE = 0x0011C017

FILE_SIZE = 300000
FT_NOW = 134000000000000000  # a FILETIME in 2025


def pattern(off, n):
    return bytes(((i * 7) & 0xff) for i in range(off, off + n))


def u16(s):
    return s.encode('utf-16-le')


def pad8(b):
    return b + b'\0' * (-len(b) % 8)


class Req:
    def __init__(self, raw):
        self.raw = raw
        (self.magic, self.hsize, self.charge, self.status, self.cmd, self.credits,
         self.flags, self.next, self.mid, self.pid, self.tree, self.sess) = \
            struct.unpack_from('<4sHHIHHIIQIIQ', raw, 0)
        self.body = raw[64:]

    def g16(self, off):
        return struct.unpack_from('<H', self.body, off)[0]

    def g32(self, off):
        return struct.unpack_from('<I', self.body, off)[0]

    def g64(self, off):
        return struct.unpack_from('<Q', self.body, off)[0]


class Rep:
    """One element of a reply frame. `hdr` overrides header fields by name:
    magic hsize charge status cmd credits flags next mid pid tree sess sig."""

    def __init__(self, req, status=ST_OK, body=b''):
        self.req = req
        self.status = status
        self.body = bytearray(body)
        self.hdr = {}
        self.raw = None       # replaces header + body altogether
        self.nopad = False

    def p8(self, off, v):
        self.body[off] = v & 0xff

    def p16(self, off, v):
        struct.pack_into('<H', self.body, off, v & 0xffff)

    def p32(self, off, v):
        struct.pack_into('<I', self.body, off, v & 0xffffffff)

    def p64(self, off, v):
        struct.pack_into('<Q', self.body, off, v & 0xffffffffffffffff)

    def error(self, status, data=b'\0', byte_count=0, ctx_count=0, ssize=9):
        self.status = status
        self.body = bytearray(struct.pack('<HBBI', ssize, ctx_count, 0, byte_count) + data)

    def encode(self, conn, related, nxt):
        if self.raw is not None:
            return bytes(self.raw)
        q = self.req
        h = dict(magic=b'\xfeSMB', hsize=64, charge=max(1, q.charge), status=self.status,
                 cmd=q.cmd, credits=max(1, min(q.credits, 64)),
                 flags=FLAG_REPLY | (FLAG_RELATED if related else 0), next=nxt,
                 mid=q.mid, pid=q.pid, tree=conn.tree if q.cmd != TREE_CONNECT else 7,
                 sess=conn.sess, sig=b'\0' * 16)
        if conn.every_hdr:
            h.update(conn.every_hdr)
        h.update(self.hdr)
        return struct.pack('<4sHHIHHIIQIIQ16s', h['magic'], h['hsize'] & 0xffff,
                           h['charge'] & 0xffff, h['status'] & 0xffffffff,
                           h['cmd'] & 0xffff, h['credits'] & 0xffff,
                           h['flags'] & 0xffffffff, h['next'] & 0xffffffff,
                           h['mid'] & 0xffffffffffffffff, h['pid'] & 0xffffffff,
                           h['tree'] & 0xffffffff, h['sess'] & 0xffffffffffffffff,
                           h['sig']) + bytes(self.body)


def nb(payload, length=None):
    return struct.pack('>I', len(payload) if length is None else length & 0xffffffff) + payload


# ── well-formed building blocks ──────────────────────────────────────────────

def ntlm_challenge(target='HOSTILE', flags=0xE28A8215, info=None, t_off=None, t_len=None,
                   i_off=None, i_len=None, sig=b'NTLMSSP\0', mtype=2):
    tn = u16(target)
    if info is None:
        info = b''
        for av, val in ((2, u16('HOSTILE')), (1, u16('HOSTILE')), (4, u16('hostile.test')),
                        (3, u16('hostile.hostile.test')), (7, struct.pack('<Q', FT_NOW))):
            info += struct.pack('<HH', av, len(val)) + val
        info += struct.pack('<HH', 0, 0)
    toff = 56
    ioff = toff + len(tn)
    return (sig + struct.pack('<I', mtype) +
            struct.pack('<HHI', len(tn) if t_len is None else t_len,
                        len(tn) if t_len is None else t_len,
                        toff if t_off is None else t_off) +
            struct.pack('<I', flags) + b'\x11\x22\x33\x44\x55\x66\x77\x88' + b'\0' * 8 +
            struct.pack('<HHI', len(info) if i_len is None else i_len,
                        len(info) if i_len is None else i_len,
                        ioff if i_off is None else i_off) +
            b'\x06\x01\x00\x00\x00\x00\x00\x0f' + tn + info)


def der(tag, content):
    n = len(content)
    if n < 0x80:
        return bytes([tag, n]) + content
    if n < 0x100:
        return bytes([tag, 0x81, n]) + content
    return bytes([tag, 0x82, n >> 8, n & 0xff]) + content


OID_SPNEGO = bytes.fromhex('06062b0601050502')
OID_NTLMSSP = bytes.fromhex('060a2b06010401823702020a')


def spnego_init():
    return der(0x60, OID_SPNEGO + der(0xa0, der(0x30, der(0xa0, der(0x30, OID_NTLMSSP)))))


def spnego_challenge(token):
    return der(0xa1, der(0x30, der(0xa0, bytes([0x0a, 1, 1])) + der(0xa1, OID_NTLMSSP) +
                         der(0xa2, der(0x04, token))))


def negotiate_body(dialect, sec=None, contexts=None, max_io=0x100000, caps=0x7):
    sec = spnego_init() if sec is None else sec
    body = struct.pack('<HHHH16sIIIIQQHHI', 65, 1, dialect, 0, b'HOSTILE-SERVER-G',
                       caps, max_io, max_io, max_io, FT_NOW, FT_NOW, 128, len(sec), 0)
    body = bytearray(body + sec)
    if dialect == 0x0311:
        if contexts is None:
            contexts = default_contexts()
        while len(body) % 8:
            body.append(0)
        struct.pack_into('<H', body, 6, len(contexts))
        struct.pack_into('<I', body, 60, 64 + len(body))
        body += encode_contexts(contexts)
    return body


def default_contexts():
    return [(1, struct.pack('<HHH', 1, 32, 1) + b'S' * 32), (2, struct.pack('<HH', 1, 2))]


def encode_contexts(contexts):
    out = b''
    for i, (ctype, data) in enumerate(contexts):
        c = struct.pack('<HHI', ctype, len(data), 0) + data
        out += pad8(c) if i + 1 < len(contexts) else c
    return out


def create_body(directory=False, size=FILE_SIZE, reparse=False):
    attrs = 0x10 if directory else 0x20
    if reparse:
        attrs |= 0x400
    return struct.pack('<HBBIQQQQQQII16sII', 89, 0, 0, 1, FT_NOW, FT_NOW, FT_NOW, FT_NOW,
                       0 if directory else (size + 4095) & ~4095, 0 if directory else size,
                       attrs, 0, b'FILEID-HOSTILE-1', 0, 0)


def close_body():
    return struct.pack('<HHIQQQQQQI', 60, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def dir_entry(name, size=0, attrs=0x20, nxt=None, name_len=None, times=FT_NOW, raw_name=None):
    n = u16(name) if raw_name is None else raw_name
    e = struct.pack('<IIQQQQQQIIIIQ', 0, 0, times, times, times, times, size,
                    ((size + 4095) & ~4095) & 0xffffffffffffffff, attrs, len(n) if name_len is None else name_len,
                    0, 0, 0x1234) + n
    e = bytearray(pad8(e))
    if nxt is not None:
        struct.pack_into('<I', e, 0, nxt)
    return e


def dir_buffer(entries):
    """entries: bytearrays from dir_entry; NextEntryOffset is filled in for
    those that left it 0, except the last."""
    out = bytearray()
    for i, e in enumerate(entries):
        if i + 1 < len(entries) and struct.unpack_from('<I', e, 0)[0] == 0:
            struct.pack_into('<I', e, 0, len(e))
        out += e
    return out


def default_dir():
    return dir_buffer([dir_entry('.', attrs=0x10), dir_entry('..', attrs=0x10),
                       dir_entry('file.bin', FILE_SIZE), dir_entry('link', 0, 0x420),
                       dir_entry('entry-with-a-longer-name.txt', 12)])


def qdir_body(buf, offset=72, length=None):
    return struct.pack('<HHI', 9, offset, len(buf) if length is None else length) + bytes(buf)


def all_info(name='\\hostile\\file.bin', directory=False, size=FILE_SIZE, name_len=None,
             times=FT_NOW):
    n = u16(name)
    return (struct.pack('<QQQQII', times, times, times, times, 0x10 if directory else 0x20, 0) +
            struct.pack('<QQIBBH', ((size + 4095) & ~4095) & 0xffffffffffffffff, size, 1, 0, 1 if directory else 0, 0) +
            struct.pack('<QIIQII', 0x1234, 0, 0x1f01ff, 0, 0, 0) +
            struct.pack('<I', len(n) if name_len is None else name_len) + n)


def qinfo_body(buf, offset=72, length=None):
    return struct.pack('<HHI', 9, offset, len(buf) if length is None else length) + bytes(buf)


def symlink_reparse(target='file.bin', tag=0xA000000C, s_off=None, s_len=None, p_off=None,
                    p_len=None, data_len=None, flags=1):
    t = u16(target)
    path = t + t
    inner = struct.pack('<HHHHI', 0 if s_off is None else s_off,
                        len(t) if s_len is None else s_len,
                        len(t) if p_off is None else p_off,
                        len(t) if p_len is None else p_len, flags) + path
    return struct.pack('<IHH', tag, (len(inner) if data_len is None else data_len) & 0xffff, 0) + inner


def ioctl_body(ctl, out, out_off=112, out_count=None, in_off=0, in_count=0, pre=b''):
    return struct.pack('<HHI16sIIIIII', 49, 0, ctl, b'FILEID-HOSTILE-1', in_off, in_count,
                       out_off, len(out) if out_count is None else out_count, 0, 0) + pre + bytes(out)


def dce_hdr(ptype, frag_len, call_id=1, pfc=3, drep=b'\x10\0\0\0', auth_len=0):
    return struct.pack('<BBBB4sHHI', 5, 0, ptype, pfc, drep, frag_len & 0xffff, auth_len, call_id)


def bind_ack(call_id=1, sec_addr=b'\\PIPE\\srvsvc\0', sec_len=None, result=0, ptype=12,
             n_results=1):
    b = struct.pack('<HHI', 4280, 4280, 0x53f0)
    b += struct.pack('<H', len(sec_addr) if sec_len is None else sec_len) + sec_addr
    b += b'\0' * (-(16 + len(b)) % 4)
    b += struct.pack('<BBH', n_results, 0, 0) + struct.pack('<HH', result, 0)
    b += bytes.fromhex('045d888aeb1cc9119fe808002b10486002000000')
    return dce_hdr(ptype, 16 + len(b), call_id) + b


def ndr_str(s, max_count=None, offset=0, actual=None, nul=True):
    data = u16(s) + (b'\0\0' if nul else b'')
    n = len(data) // 2
    out = struct.pack('<III', n if max_count is None else max_count, offset,
                      n if actual is None else actual) + data
    return out + b'\0' * (-len(out) % 4)


def share_stub(shares=(('public', 0, 'Public share'), ('IPC$', 0x80000003, 'IPC Service')),
               level=1, sw=None, count=None, max_count=None, total=None, werror=0,
               strings=None, ctr_ref=0x20000, buf_ref=0x20004, refs=None):
    n = len(shares)
    out = struct.pack('<III', level, level if sw is None else sw, ctr_ref)
    out += struct.pack('<II', n if count is None else count, buf_ref)
    out += struct.pack('<I', n if max_count is None else max_count)
    for i, (name, stype, remark) in enumerate(shares):
        r = refs[i] if refs else (0x20008 + 8 * i, 0x2000c + 8 * i)
        out += struct.pack('<III', r[0], stype, r[1])
    if strings is None:
        for name, stype, remark in shares:
            out += ndr_str(name) + ndr_str(remark)
    else:
        out += strings
    out += struct.pack('<III', n if total is None else total, 0, werror)
    return out


def dce_response(stub, call_id=2, pfc=3, frag_len=None, drep=b'\x10\0\0\0', ptype=2,
                 auth_len=0, alloc_hint=None):
    body = struct.pack('<IHBB', len(stub) if alloc_hint is None else alloc_hint, 0, 0, 0) + stub
    return dce_hdr(ptype, 16 + len(body) if frag_len is None else frag_len, call_id, pfc,
                   drep, auth_len) + body


# ── the server ───────────────────────────────────────────────────────────────

class Conn:
    def __init__(self, sock, case, log):
        self.sock = sock
        self.case = case
        self.log = log
        self.dialect = case.get('dialect', 0x0210)
        self.sess = 0x0000040000000401
        self.tree = 0
        self.count = {}
        self.qdir_calls = 0
        self.ss_legs = 0
        self.ipc = False
        self.dce_calls = 0
        self.pipe_data = b''
        self.every_hdr = dict(case.get('every_hdr') or {})
        self.stalled = False
        self.fired = False
        self.served = 0

    # default handlers: return a Rep
    def handle(self, q):
        h = self.case.get('handlers', {}).get(q.cmd)
        if h:
            r = h(self, q)
            if r is not None:
                return r
        return getattr(self, 'do_' + CMDNAME[q.cmd], self.do_unknown)(q)

    def do_unknown(self, q):
        r = Rep(q)
        r.error(ST_NOT_SUPPORTED)
        return r

    def do_negotiate(self, q):
        if 'dialect' not in self.case:
            n = q.g16(2)
            offered = [q.g16(36 + 2 * i) for i in range(n)]
            self.dialect = 0x0210 if 0x0210 in offered else max(offered or [0x0210])
        return Rep(q, ST_OK, negotiate_body(self.dialect))

    def do_session_setup(self, q):
        self.ss_legs += 1
        if self.ss_legs == 1:
            tok = ntlm_challenge()
            return Rep(q, ST_MORE, struct.pack('<HHHH', 9, 0, 72, len(tok)) + tok)
        return Rep(q, ST_OK, struct.pack('<HHHH', 9, 0, 72, 0))

    def do_logoff(self, q):
        return Rep(q, ST_OK, struct.pack('<HH', 4, 0))

    def do_tree_connect(self, q):
        off, ln = q.g16(4), q.g16(6)
        path = q.raw[off:off + ln].decode('utf-16-le', 'replace')
        self.ipc = path.upper().endswith('IPC$')
        self.tree = 7
        return Rep(q, ST_OK, struct.pack('<HBBIII', 16, 2 if self.ipc else 1, 0, 0, 0, 0x1f01ff))

    def do_tree_disconnect(self, q):
        return Rep(q, ST_OK, struct.pack('<HH', 4, 0))

    def name_of(self, q):
        off, ln = q.g16(44), q.g16(46)
        return q.raw[off:off + ln].decode('utf-16-le', 'replace')

    def do_create(self, q):
        name = self.name_of(q)
        opts = q.g32(40)
        if name.endswith('gone.bin'):
            r = Rep(q)
            r.error(0xC0000034)
            return r
        directory = bool(opts & 1) or name.endswith('sub') or '\\' not in name and \
            not name.endswith(('.bin', 'link', 'srvsvc'))
        return Rep(q, ST_OK, create_body(directory, reparse=name.endswith('link')))

    def do_close(self, q):
        return Rep(q, ST_OK, close_body())

    def do_flush(self, q):
        return Rep(q, ST_OK, struct.pack('<HH', 4, 0))

    def do_echo(self, q):
        return Rep(q, ST_OK, struct.pack('<HH', 4, 0))

    def do_read(self, q):
        length, offset = q.g32(4), q.g64(8)
        r = Rep(q)
        if self.ipc:
            data, self.pipe_data = self.pipe_data[:length], self.pipe_data[length:]
        elif offset >= FILE_SIZE:
            r.error(ST_EOF)
            return r
        else:
            data = pattern(offset, min(length, FILE_SIZE - offset))
        r.body = bytearray(struct.pack('<HBBIII', 17, 0x50, 0, len(data), 0, 0) + data)
        return r

    def do_write(self, q):
        return Rep(q, ST_OK, struct.pack('<HHIIHH', 17, 0, q.g32(4), 0, 0, 0))

    def do_query_directory(self, q):
        self.qdir_calls += 1
        r = Rep(q)
        if self.qdir_calls == 1:
            r.body = bytearray(qdir_body(default_dir()))
        else:
            r.error(ST_NO_MORE_FILES)
        return r

    def do_query_info(self, q):
        itype, iclass = q.body[2], q.body[3]
        if itype == 1 and iclass == 18:
            buf = all_info()
        elif itype == 1 and iclass == 35:
            buf = struct.pack('<II', 0x20, 0)
        elif itype == 2 and iclass == 7:
            buf = struct.pack('<QQQII', 1000000, 500000, 500000, 8, 512)
        elif itype == 2 and iclass == 3:
            buf = struct.pack('<QQII', 1000000, 500000, 8, 512)
        else:
            r = Rep(q)
            r.error(0xC0000003)
            return r
        return Rep(q, ST_OK, qinfo_body(buf))

    def do_set_info(self, q):
        return Rep(q, ST_OK, struct.pack('<H', 2))

    def do_ioctl(self, q):
        ctl = q.g32(4)
        if ctl == FSCTL_GET_REPARSE_POINT:
            return Rep(q, ST_OK, ioctl_body(ctl, symlink_reparse()))
        if ctl == FSCTL_PIPE_TRANSCEIVE:
            self.dce_calls += 1
            ioff, icnt = q.g32(24), q.g32(28)
            call_id = struct.unpack_from('<I', q.raw, ioff + 12)[0] if icnt >= 16 else 1
            if self.dce_calls == 1:
                out = bind_ack(call_id)
            else:
                out = dce_response(share_stub(), call_id)
            return Rep(q, ST_OK, ioctl_body(ctl, out))
        r = Rep(q)
        r.error(ST_NOT_SUPPORTED)
        return r

    # frame loop
    def serve(self):
        buf = b''
        s = self.sock
        while True:
            try:
                d = s.recv(1 << 20)
            except OSError:
                return
            if not d:
                return
            buf += d
            while len(buf) >= 4:
                ln = struct.unpack('>I', buf[:4])[0] & 0xffffff
                if len(buf) < 4 + ln:
                    break
                frame, buf = buf[4:4 + ln], buf[4 + ln:]
                if self.stalled:
                    continue
                if not self.on_frame(frame):
                    return

    def on_frame(self, frame):
        case = self.case
        reqs = []
        off = 0
        while off + 64 <= len(frame):
            nxt = struct.unpack_from('<I', frame, off + 20)[0]
            end = off + nxt if nxt else len(frame)
            reqs.append(Req(frame[off:end]))
            if not nxt:
                break
            off = end
        reps = []
        hit = None
        for q in reqs:
            if q.cmd == CANCEL:
                continue
            self.count[q.cmd] = self.count.get(q.cmd, 0) + 1
            r = self.handle(q)
            if (not self.fired and case.get('cmd') == q.cmd and
                    (case.get('nth', 1) is None or
                     self.count[q.cmd] == case.get('nth', 1)) and
                    (not case.get('ipc_only') or self.ipc) and
                    (case.get('when') is None or case['when'](self, q))):
                self.fired = True
                hit = r
                print('FIRED', flush=True)
                if case.get('rep'):
                    case['rep'](r, q, self)
            reps.append(r)
        if not reps:
            return True
        parts = []
        for i, r in enumerate(reps):
            last = i + 1 == len(reps)
            raw_len = 64 + len(r.body) if r.raw is None else len(r.raw)
            padded = raw_len if (last or r.nopad) else (raw_len + 7) & ~7
            e = r.encode(self, i > 0 and bool(r.req.flags & FLAG_RELATED),
                         0 if last else padded)
            parts.append(e + b'\0' * (padded - len(e)))
        payload = b''.join(parts)
        chunks, action = [nb(payload)], None
        if hit is not None and case.get('frame'):
            chunks, action = case['frame'](payload, self, parts, reps.index(hit))
        try:
            for c in chunks:
                if isinstance(c, (int, float)):
                    time.sleep(c)
                else:
                    self.sock.sendall(c)
        except OSError:
            return False
        if action == 'close':
            return False
        if action == 'stall':
            self.stalled = True
        return True


def serve(port, case, once=False, log=print):
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(('127.0.0.1', port))
    ls.listen(8)
    print('PORT %d' % ls.getsockname()[1], flush=True)

    def one(c):
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            Conn(c, case, log).serve()
        except Exception as e:  # a malformed request from a confused client
            print('server error: %r' % (e,), file=sys.stderr, flush=True)
        finally:
            try:
                c.close()
            except OSError:
                pass

    while True:
        c, _ = ls.accept()
        threading.Thread(target=one, args=(c,), daemon=True).start()


def main():
    from hostile_cases import CASES
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--case', default='none')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    if a.list:
        if a.json:
            print(json.dumps([dict(name=n, ops=c.get('ops', 'e'), ver=c.get('ver', 0),
                                   wall=c.get('wall', 0),
                                   group=c.get('group', ''), desc=c.get('desc', ''))
                              for n, c in CASES.items()], indent=1))
        else:
            for n, c in CASES.items():
                print('%-44s %-8s %s' % (n, c.get('ops', 'e'), c.get('desc', '')))
        return
    if a.case not in CASES:
        sys.exit('unknown case %s' % a.case)
    import hostile_server
    hostile_server.serve(a.port, CASES[a.case])


if __name__ == '__main__':
    main()
