# Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
# All rights reserved.
# Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.
"""The malformed replies hostile_server.py can give, one per case.

A case is a dict: `ops` (what the client must do to reach it: the letters
of harness.c), `cmd`/`nth` (which reply is malformed: the nth reply to that
command on a connection; `when` narrows it further), then `rep` (edits the
reply element), `frame` (replaces what goes on the wire for the frame that
holds it) or `handlers` (replaces how a command is answered for the whole
run). `ver` is the dialect the client is told to ask for (0: any; the
server then picks 2.1).
"""
import os
import struct

from hostile_server import *  # noqa: F401,F403
from hostile_server import (Rep, Req, nb, pad8, u16, pattern, ntlm_challenge, der, spnego_init,
                            spnego_challenge, negotiate_body, default_contexts,
                            dir_entry, dir_buffer, default_dir, qdir_body, all_info,
                            qinfo_body, symlink_reparse, ioctl_body, dce_hdr, bind_ack,
                            ndr_str, share_stub, dce_response, OID_NTLMSSP, OID_SPNEGO)

CASES = {}


def C(name, ops, cmd=None, rep=None, frame=None, nth=1, group='', desc='', **kw):
    assert name not in CASES, name
    d = dict(ops=ops, cmd=cmd, rep=rep, frame=frame, nth=nth, group=group, desc=desc)
    d.update(kw)
    CASES[name] = d


C('none', 'dsorwfycklvemniuE', group='baseline', desc='well-behaved server (control)')
C('none_311', 'dsorwfycklvemniuE', group='baseline', ver=0x0311,
  desc='well-behaved server, SMB 3.1.1 (control)')
C('none_302', 'dsorwfycklvemniuE', group='baseline', ver=0x0302,
  desc='well-behaved server, SMB 3.0.2 (control)')


def hdr(conn, cmd, mid, status=0, flags=1, credits=1, nxt=0, magic=b'\xfeSMB', hsize=64):
    return struct.pack('<4sHHIHHIIQIIQ16s', magic, hsize, 1, status, cmd, credits, flags, nxt,
                       mid & 0xffffffffffffffff, 0, conn.tree, conn.sess, b'\0' * 16)


# ── frame level ─────────────────────────────────────────────────────────────

def f_nb(length=None, cut=None, action=None, delta=None):
    def f(payload, conn, parts, idx):
        ln = length if length is not None else len(payload) + (delta or 0)
        data = payload if cut is None else payload[:cut]
        return [nb(data, ln)], action
    return f


for where, cmd, ops in (('negotiate', NEGOTIATE, 'e'), ('echo', ECHO, 'e')):
    g = 'netbios'
    C('nb_len_00ffffff_stall_' + where, ops, cmd, frame=f_nb(0x00FFFFFF, action='stall'), group=g,
      desc='NetBIOS length 0x00FFFFFF, only the real reply sent, then silence')
    C('nb_len_00ffffff_close_' + where, ops, cmd, frame=f_nb(0x00FFFFFF, action='close'), group=g,
      desc='NetBIOS length 0x00FFFFFF, only the real reply sent, then close')
    C('nb_len_01000000_' + where, ops, cmd, frame=f_nb(0x01000000, action='stall'), group=g,
      desc='NetBIOS length exactly 16 MiB')
    C('nb_len_01000001_' + where, ops, cmd, frame=f_nb(0x01000001, action='stall'), group=g,
      desc='NetBIOS length 16 MiB + 1')
    C('nb_len_ffffffff_' + where, ops, cmd, frame=f_nb(0xFFFFFFFF, action='stall'), group=g,
      desc='NetBIOS length 0xFFFFFFFF')
    C('nb_len_7fffffff_' + where, ops, cmd, frame=f_nb(0x7FFFFFFF, action='stall'), group=g,
      desc='NetBIOS length 0x7FFFFFFF')
    C('nb_len_0_' + where, ops, cmd, frame=f_nb(0), group=g, desc='NetBIOS length 0')
    C('nb_len_4_' + where, ops, cmd, frame=f_nb(4, cut=4), group=g,
      desc='NetBIOS length 4, 4 bytes sent')
    C('nb_len_63_' + where, ops, cmd, frame=f_nb(63, cut=63), group=g,
      desc='NetBIOS length 63 (one short of an SMB2 header)')
    C('nb_len_64_hdr_only_' + where, ops, cmd, frame=f_nb(64, cut=64), group=g,
      desc='NetBIOS length 64: a header with no body')
    C('nb_len_plus100_stall_' + where, ops, cmd, frame=f_nb(delta=100, action='stall'), group=g,
      desc='NetBIOS length 100 more than sent, then silence')
    C('nb_len_minus8_' + where, ops, cmd, frame=f_nb(delta=-8), group=g,
      desc='NetBIOS length 8 less than sent: the tail is read as the next frame')
    C('eof_after_nb_len_' + where, ops, cmd, frame=f_nb(cut=0, action='close'), group=g,
      desc='EOF right after the 4 length bytes')
    C('eof_mid_header_' + where, ops, cmd, frame=f_nb(cut=30, action='close'), group=g,
      desc='EOF 30 bytes into the SMB2 header')
    C('eof_mid_body_' + where, ops, cmd, frame=f_nb(cut=66, action='close'), group=g,
      desc='EOF 2 bytes into the reply body')
    C('eof_2_bytes_of_len_' + where, ops, cmd,
      frame=lambda p, c, parts, i: ([b'\0\0'], 'close'), group=g,
      desc='EOF after 2 of the 4 length bytes')
    C('magic_ff_smb1_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(magic=b'\xffSMB'),
      group='header', desc='ProtocolId 0xFF SMB (SMB1)')
    C('magic_garbage_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(magic=b'XSMB'),
      group='header', desc='ProtocolId XSMB')
    C('magic_zero_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(magic=b'\0\0\0\0'),
      group='header', desc='ProtocolId 0')
    for v in (0, 63, 65, 0xffff):
        C('hdr_structsize_%d_%s' % (v, where), ops, cmd,
          rep=lambda r, q, c, v=v: r.hdr.update(hsize=v), group='header',
          desc='header StructureSize %d' % v)
    C('hdr_not_a_reply_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(flags=0),
      group='header', desc='SERVER_TO_REDIR flag clear')
    C('hdr_wrong_command_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(cmd=WRITE),
      group='header', desc='reply carries the command WRITE')
    C('hdr_command_999_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(cmd=999),
      group='header', desc='reply carries command 999')
    C('hdr_wrong_mid_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(mid=q.mid + 1000),
      group='header', desc='MessageId of no request (the real reply never comes)')
    C('hdr_mid_ffffffff_' + where, ops, cmd,
      rep=lambda r, q, c: r.hdr.update(mid=0xffffffffffffffff),
      group='header', desc='MessageId 0xFFFFFFFFFFFFFFFF')
    C('hdr_signed_garbage_' + where, ops, cmd,
      rep=lambda r, q, c: r.hdr.update(flags=1 | 8, sig=b'\xaa' * 16),
      group='header', desc='SIGNED flag with a garbage signature')
    C('hdr_async_flag_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(flags=1 | 2),
      group='header', desc='ASYNC flag on a final reply')
    C('hdr_next_command_8_' + where, ops, cmd, rep=lambda r, q, c: r.hdr.update(next=8),
      group='compound', desc='single reply with NextCommand 8 (inside its own header)')
    C('hdr_next_command_end_' + where, ops, cmd,
      rep=lambda r, q, c: r.hdr.update(next=(64 + len(r.body) + 7) & ~7), group='compound',
      desc='single reply with NextCommand at the end of the frame')
    C('hdr_next_command_ffffffff_' + where, ops, cmd,
      rep=lambda r, q, c: r.hdr.update(next=0xffffffff), group='compound',
      desc='single reply with NextCommand 0xFFFFFFFF')


# unsolicited frames ahead of the real reply
def unsol(make):
    return lambda payload, conn, parts, idx: ([nb(make(conn)), nb(payload)], None)


C('unsolicited_echo_reply', 'e', ECHO,
  frame=unsol(lambda c: hdr(c, ECHO, 0x7777) + struct.pack('<HH', 4, 0)), group='unsolicited',
  desc='an ECHO reply nobody asked for, then the real one')
C('unsolicited_big_unknown', 'e', ECHO,
  frame=unsol(lambda c: hdr(c, READ, 0x7777) + b'\xaa' * 200000), group='unsolicited',
  desc='200 kB reply with an unknown MessageId, then the real one')
C('unsolicited_oplock_break', 'e', ECHO,
  frame=unsol(lambda c: hdr(c, OPLOCK_BREAK, -1) + struct.pack('<HBBI16s', 24, 0, 0, 0, b'F' * 16)),
  group='unsolicited', desc='oplock break notification, then the real reply')
C('unsolicited_lease_break', 'e', ECHO,
  frame=unsol(lambda c: hdr(c, OPLOCK_BREAK, -1) +
              struct.pack('<HHI16sIIIII', 44, 0, 0, b'K' * 16, 7, 1, 0, 0, 0)),
  group='unsolicited', desc='lease break notification, then the real reply')
for ssz, blen in ((0, 24), (24, 4), (44, 20), (36, 36), (1000, 24), (0xffff, 2), (24, 2), (44, 2)):
    C('unsolicited_break_ss%d_len%d' % (ssz, blen), 'e', ECHO,
      frame=unsol(lambda c, ssz=ssz, blen=blen: hdr(c, OPLOCK_BREAK, -1) +
                  (struct.pack('<H', ssz) + b'\x01' * 100)[:blen]),
      group='unsolicited',
      desc='break notification with StructureSize %d and %d body bytes' % (ssz, blen))
C('unsolicited_oplock_break_flood', 'e', ECHO,
  frame=lambda payload, conn, parts, idx: (
      [nb(hdr(conn, OPLOCK_BREAK, -1) + struct.pack('<HBBI16s', 24, 0, 0, 0, b'F' * 16))] * 3000
      + [nb(payload)], None),
  group='unsolicited', desc='3000 oplock break notifications, then the real reply')

for _n in (1, 2, 3, 5, 10):
    C('unsolicited_oplock_break_x%d' % _n, 'e', ECHO,
      frame=lambda payload, conn, parts, idx, _n=_n: (
          [nb(hdr(conn, OPLOCK_BREAK, -1) + struct.pack('<HBBI16s', 24, 0, 0, 0, b'F' * 16))] * _n
          + [nb(payload)], None),
      group='unsolicited', desc='%d oplock break notification(s), then the real reply' % _n)



# interim (STATUS_PENDING) replies
def pend(conn, q, body=b'', flags=3):
    return struct.pack('<4sHHIHHIIQQQ16s', b'\xfeSMB', 64, 1, ST_PENDING, q.cmd, 1, flags, 0,
                       q.mid, 0x55, conn.sess, b'\0' * 16) + body


ERRBODY = struct.pack('<HBBIB', 9, 0, 0, 0, 0)
C('pending_then_reply', 'e', ECHO,
  frame=lambda p, c, parts, i: ([nb(pend(c, Req(parts[i]), ERRBODY)), nb(p)], None),
  group='pending', desc='interim STATUS_PENDING, then the reply (legal)')
C('pending_header_only_then_reply', 'e', ECHO,
  frame=lambda p, c, parts, i: ([nb(pend(c, Req(parts[i]))), nb(p)], None),
  group='pending', desc='header-only interim reply, then the reply')
C('pending_forever', 'e', ECHO,
  frame=lambda p, c, parts, i: ([nb(pend(c, Req(parts[i]), ERRBODY))] * 500, 'stall'),
  group='pending', desc='500 interim replies and never a final one')
C('pending_big_pad', 'e', ECHO,
  frame=lambda p, c, parts, i: ([nb(pend(c, Req(parts[i]), b'\xaa' * 500000)), nb(p)], None),
  group='pending', desc='interim reply with 500 kB of body, then the reply')
C('pending_unknown_mid', 'e', ECHO,
  frame=lambda p, c, parts, i: ([nb(hdr(c, ECHO, 0x9999, status=ST_PENDING, flags=3) + ERRBODY),
                                 nb(p)], None),
  group='pending', desc='interim reply for an unknown MessageId, then the reply')
C('pending_wrong_command', 'e', ECHO,
  frame=lambda p, c, parts, i: ([nb(hdr(c, READ, Req(parts[i]).mid, status=ST_PENDING, flags=3)
                                    + ERRBODY), nb(p)], None),
  group='pending', desc='interim reply naming another command')


# transform (encryption) headers nobody negotiated
def trfm(conn, n=128, flags=1, sess=None, orig=None, body=None):
    body = os.urandom(n) if body is None else body
    return (b'\xfdSMB' + b'\x11' * 16 + b'\x22' * 16 +
            struct.pack('<IHHQ', len(body) if orig is None else orig, 0, flags,
                        conn.sess if sess is None else sess) + body)


for ver in (0x0210, 0x0302, 0x0311):
    t = '%04x' % ver
    C('transform_garbage_' + t, 'e', ECHO, ver=ver,
      frame=lambda p, c, parts, i: ([nb(trfm(c))], 'stall'), group='transform',
      desc='a transform header with a random payload instead of the reply')
    C('transform_orig_size_mismatch_' + t, 'e', ECHO, ver=ver,
      frame=lambda p, c, parts, i: ([nb(trfm(c, orig=0x7fffffff))], 'stall'), group='transform',
      desc='transform header whose OriginalMessageSize is 2 GiB')
    C('transform_short_' + t, 'e', ECHO, ver=ver,
      frame=lambda p, c, parts, i: ([nb(trfm(c, n=12))], 'stall'), group='transform',
      desc='transform header with 12 payload bytes')
    C('transform_other_session_' + t, 'e', ECHO, ver=ver,
      frame=lambda p, c, parts, i: ([nb(trfm(c, sess=1))], 'stall'), group='transform',
      desc='transform header for another session')
    C('transform_flags_0_' + t, 'e', ECHO, ver=ver,
      frame=lambda p, c, parts, i: ([nb(trfm(c, flags=0))], 'stall'), group='transform',
      desc='transform header with Flags 0')
    C('transform_plain_inside_' + t, 'e', ECHO, ver=ver,
      frame=lambda p, c, parts, i: ([nb(trfm(c, body=p + b'\0' * 64))], 'stall'),
      group='transform', desc='transform header wrapping the plaintext reply')
C('transform_at_negotiate', 'e', NEGOTIATE,
  frame=lambda p, c, parts, i: ([nb(trfm(c))], 'stall'), group='transform',
  desc='a transform header as the negotiate reply')

# credits
C('credits_0_everywhere', 'e', group='credits', every_hdr=dict(credits=0),
  desc='every reply grants 0 credits')
C('credits_0_after_tree_connect', 'orc', TREE_CONNECT, group='credits',
  rep=lambda r, q, c: c.every_hdr.update(credits=0),
  desc='0 credits from the tree connect on')
C('credits_ffff_everywhere', 'dsorwfyckve', group='credits', every_hdr=dict(credits=0xffff),
  desc='every reply grants 65535 credits')
C('credit_charge_ffff', 'orc', READ, rep=lambda r, q, c: r.hdr.update(charge=0xffff), nth=2,
  group='credits', desc='reply with CreditCharge 65535')

# ── generic per command: StructureSize, truncation, status against shape ─────
PER_CMD = [
    (NEGOTIATE, 'e', 1), (SESSION_SETUP, 'e', 1), (SESSION_SETUP, 'e', 2),
    (TREE_CONNECT, 'e', 1), (CREATE, 'oc', 1), (CLOSE, 'oc', 1),
    (FLUSH, 'oyc', 1), (READ, 'orc', 2), (WRITE, 'owc', 2), (ECHO, 'e', 1),
    (QUERY_DIRECTORY, 'd', 1), (QUERY_INFO, 'ofc', 1), (SET_INFO, 'otc', 1),
    (IOCTL, 'k', 1), (TREE_DISCONNECT, 'e', 1),
]


def v_ss(v):
    return lambda r, q, c: r.p16(0, v) if len(r.body) >= 2 else None


def v_trunc(n):
    def f(r, q, c):
        r.body = r.body[:n]
    return f


def v_status(st):
    return lambda r, q, c: setattr(r, 'status', st)


def v_errbody(st):
    def f(r, q, c):
        r.error(st)
        r.status = st
    return f


def v_tail(r, q, c):
    r.body += b'\xaa' * 64


for cmd, ops, nth in PER_CMD:
    n = CMDNAME[cmd] + ('%d' % nth if cmd == SESSION_SETUP else '')
    g = 'per-command'
    for v in (0, 0xffff):
        C('%s_structsize_%d' % (n, v), ops, cmd, v_ss(v), nth=nth, group=g,
          desc='%s reply body StructureSize %d' % (n, v))
    C('%s_structsize_plus2' % n, ops, cmd,
      lambda r, q, c: r.p16(0, struct.unpack_from('<H', r.body, 0)[0] + 2), nth=nth, group=g,
      desc='%s reply body StructureSize + 2' % n)
    C('%s_structsize_error9' % n, ops, cmd, v_ss(9), nth=nth, group=g,
      desc='%s reply body StructureSize 9 (an error reply) with its own status' % n)
    C('%s_body_cut_to_4' % n, ops, cmd, v_trunc(4), nth=nth, group=g,
      desc='%s reply cut to 4 body bytes (lengths consistent)' % n)
    C('%s_body_cut_to_1' % n, ops, cmd, v_trunc(1), nth=nth, group=g,
      desc='%s reply cut to 1 body byte' % n)
    C('%s_header_only' % n, ops, cmd, v_trunc(0), nth=nth, group=g,
      desc='%s reply with no body at all' % n)
    C('%s_error_status_success_body' % n, ops, cmd, v_status(ST_ACCESS_DENIED), nth=nth, group=g,
      desc='%s: STATUS_ACCESS_DENIED over a success-shaped body' % n)
    C('%s_success_status_error_body' % n, ops, cmd, v_errbody(ST_OK), nth=nth, group=g,
      desc='%s: STATUS_SUCCESS over a 9-byte error body' % n)
    C('%s_warning_status_error_body' % n, ops, cmd, v_errbody(ST_BUFFER_OVERFLOW), nth=nth,
      group=g, desc='%s: STATUS_BUFFER_OVERFLOW (a warning) over an error body' % n)
    C('%s_info_status_0x40000000' % n, ops, cmd, v_status(0x40000000), nth=nth, group=g,
      desc='%s: informational status 0x40000000 over a success body' % n)
    C('%s_junk_tail' % n, ops, cmd, v_tail, nth=nth, group=g,
      desc='%s reply followed by 64 bytes of 0xAA in the same PDU' % n)

# ── error replies ───────────────────────────────────────────────────────────
for bc, data, what in ((0xffffffff, b'\0', '0xFFFFFFFF'), (0x7fffffff, b'\0', '0x7FFFFFFF'),
                       (1000, b'\0' * 8, '1000 with 8 bytes present'),
                       (8, b'', '8 with none present'), (1, b'\0', '1')):
    C('error_bytecount_%x_%d' % (bc, len(data)), 'e', ECHO,
      lambda r, q, c, bc=bc, data=data: r.error(ST_ACCESS_DENIED, data, bc), group='error',
      desc='error reply with ByteCount ' + what)
C('error_structsize_8', 'e', ECHO, lambda r, q, c: r.error(ST_ACCESS_DENIED, ssize=8),
  group='error', desc='error reply with StructureSize 8')
C('error_context_count_255', 'e', ECHO,
  lambda r, q, c: r.error(ST_ACCESS_DENIED, b'\0' * 16, 16, ctx_count=255), group='error',
  desc='error reply with ErrorContextCount 255')
C('error_big_data', 'e', ECHO,
  lambda r, q, c: r.error(ST_ACCESS_DENIED, b'\xaa' * 100000, 100000), group='error',
  desc='error reply with 100 kB of ErrorData')
for st, nm in ((0xC0000203, 'user_session_deleted'), (0xC000035C, 'network_session_expired'),
               (0xC000020C, 'connection_disconnected'), (0xFFFFFFFF, 'ffffffff'),
               (0x80000000, '80000000'), (0xC0000000, 'c0000000')):
    C('error_status_' + nm, 'orc', READ, lambda r, q, c, st=st: r.error(st), nth=2, group='error',
      desc='READ fails with status 0x%08X' % st)


# symlink error responses on open (libsmb2 follows them)
def symerr(target='file.bin', unparsed=0, flags=1, s_off=0, s_len=None, p_off=None, p_len=None,
           tag=0x4C4D5953, rtag=0xA000000C, sl_len=None, rd_len=None, ctx=0, bc=None, cut=None):
    t = u16(target)
    path = t + t
    inner = struct.pack('<HHHHHI', unparsed, s_off, len(t) if s_len is None else s_len,
                        len(t) if p_off is None else p_off, len(t) if p_len is None else p_len,
                        flags) + path
    d = struct.pack('<III', (len(inner) + 10) if sl_len is None else sl_len, tag, rtag)
    d += struct.pack('<H', len(inner) - 2 if rd_len is None else rd_len) + inner
    if ctx:
        d = struct.pack('<II', len(d), 0) + d
    if cut is not None:
        d = d[:cut]

    def f(r, q, c):
        r.error(ST_STOPPED_ON_SYMLINK, d or b'\0', len(d) if bc is None else bc, ctx_count=ctx)
    return f


SYM = [('ok_relative', dict()), ('absolute', dict(flags=0, target='\\??\\C:\\x')),
       ('unparsed_huge', dict(unparsed=0xffff)), ('unparsed_odd', dict(unparsed=3)),
       ('subname_len_ffff', dict(s_len=0xffff)), ('subname_off_ffff', dict(s_off=0xffff)),
       ('printname_len_ffff', dict(p_len=0xffff)), ('printname_off_ffff', dict(p_off=0xffff)),
       ('subname_odd_len', dict(s_len=5)), ('cut_8', dict(cut=8)), ('cut_12', dict(cut=12)),
       ('cut_20', dict(cut=20)), ('cut_27', dict(cut=27)), ('bytecount_4', dict(bc=4)),
       ('wrong_tag', dict(tag=0x41414141)), ('wrong_reparse_tag', dict(rtag=0xA0000003)),
       ('symlink_length_huge', dict(sl_len=0xffffffff)),
       ('reparse_data_length_huge', dict(rd_len=0xffff)),
       ('target_dotdot', dict(target='..\\..\\..\\etc\\passwd')),
       ('target_4000_chars', dict(target='A' * 4000)),
       ('target_empty', dict(target=''))]
for nm, kw in SYM:
    C('open_symlink_error_' + nm, 'oc', CREATE, symerr(**kw), group='symlink-error',
      desc='open answered STATUS_STOPPED_ON_SYMLINK: ' + nm.replace('_', ' '))
C('open_symlink_error_ctx_311', 'oc', CREATE, symerr(ctx=1), ver=0x0311, group='symlink-error',
  desc='STOPPED_ON_SYMLINK with a 3.1.1 error context')
C('open_symlink_error_ctx_311_cut', 'oc', CREATE, symerr(ctx=1, cut=10), ver=0x0311,
  group='symlink-error', desc='STOPPED_ON_SYMLINK with a truncated 3.1.1 error context')


def h_symloop(conn, q):
    conn.served += 1
    r = Rep(q)
    symerr(target='file.bin')(r, q, conn)
    return r


C('open_symlink_loop', 'oc', group='symlink-error', handlers={CREATE: h_symloop}, wall=15,
  desc='every open is answered STOPPED_ON_SYMLINK to the same name (a loop)')


# ── READ ────────────────────────────────────────────────────────────────────
def read_rep(datalen=None, data=None, off=0x50, remaining=0, status=None, ssize=17):
    def f(r, q, c):
        asked = q.g32(4)
        d = pattern(0, asked) if data is None else (data(asked) if callable(data) else data)
        dl = len(d) if datalen is None else (datalen(asked) if callable(datalen) else datalen)
        r.body = bytearray(struct.pack('<HBBIII', ssize, off, 0, dl, remaining, 0) + d)
        r.status = ST_OK if status is None else status
    return f


R = 'read'
# the 2nd read asks 100 bytes into a 100 byte heap buffer; the 5th asks 200000
C('read_datalen_gt_asked_all_sent', 'orc', READ, read_rep(data=lambda a: b'\xee' * (a + 100)),
  nth=2, group=R, desc='asked 100: DataLength 200 and 200 bytes really sent')
C('read_datalen_asked_plus1', 'orc', READ, read_rep(data=lambda a: b'\xee' * (a + 1)), nth=2,
  group=R, desc='asked 100: DataLength 101, 101 bytes sent')
C('read_datalen_64k_for_1', 'orc', READ, read_rep(data=lambda a: b'\xee' * 65536), nth=1,
  group=R, desc='asked 1: DataLength 65536, 65536 bytes sent')
C('read_datalen_1m_for_100', 'orc', READ, read_rep(data=lambda a: b'\xee' * (1 << 20)), nth=2,
  group=R, desc='asked 100: 1 MiB sent')
C('read_datalen_gt_sent_consistent', 'orc', READ,
  read_rep(datalen=lambda a: a, data=lambda a: b'\xee' * 10), nth=3, group=R,
  desc='asked 4096: DataLength 4096, 10 bytes in the PDU (NetBIOS length honest)')
C('read_datalen_gt_sent_stall', 'orc', READ,
  read_rep(datalen=lambda a: a, data=lambda a: b'\xee' * 10), nth=3, group=R,
  frame=lambda p, c, parts, i: ([nb(p, len(p) + 4086)], 'stall'),
  desc='asked 4096: DataLength 4096, NetBIOS length says so too, 10 bytes sent, silence')
C('read_datalen_gt_sent_close', 'orc', READ,
  read_rep(datalen=lambda a: a, data=lambda a: b'\xee' * 10), nth=3, group=R,
  frame=lambda p, c, parts, i: ([nb(p, len(p) + 4086)], 'close'),
  desc='asked 4096: DataLength 4096, 10 bytes sent, then EOF')
C('read_datalen_ffffffff', 'orc', READ, read_rep(datalen=0xffffffff), nth=2, group=R,
  desc='DataLength 0xFFFFFFFF')
C('read_datalen_80000000', 'orc', READ, read_rep(datalen=0x80000000), nth=2, group=R,
  desc='DataLength 0x80000000')
C('read_datalen_0_with_data', 'orc', READ, read_rep(datalen=0), nth=2, group=R,
  desc='DataLength 0 while 100 bytes follow')
C('read_datalen_lt_sent', 'orc', READ, read_rep(datalen=10), nth=2, group=R,
  desc='DataLength 10 while 100 bytes follow')
for off in (0, 0x10, 0x40, 0x4f, 0x51, 0x58, 0xff):
    C('read_dataoffset_%02x' % off, 'orc', READ, read_rep(off=off), nth=2, group=R,
      desc='DataOffset 0x%02x (0x50 is the valid one)' % off)
C('read_dataoffset_58_padded', 'orc', READ,
  read_rep(off=0x58, data=lambda a: b'\0' * 8 + b'\xee' * a, datalen=lambda a: a), nth=2,
  group=R, desc='DataOffset 0x58 with 8 padding bytes (legal for a server)')
C('read_short_legit', 'orc', READ, read_rep(data=lambda a: b'\xee' * 7), nth=2, group=R,
  desc='asked 100: 7 bytes returned (a legal short read)')
C('read_eof_error_body', 'orc', READ, lambda r, q, c: r.error(ST_EOF), nth=2, group=R,
  desc='STATUS_END_OF_FILE with the usual error body (legal)')
C('read_eof_with_read_body', 'orc', READ, read_rep(status=ST_EOF), nth=2, group=R,
  desc='STATUS_END_OF_FILE over a READ-shaped body with 100 data bytes')
C('read_eof_with_read_body_big', 'orc', READ,
  read_rep(status=ST_EOF, data=lambda a: b'\xee' * 5000), nth=2, group=R,
  desc='STATUS_END_OF_FILE over a READ-shaped body with 5000 data bytes')
C('read_eof_bytecount_huge', 'orc', READ,
  lambda r, q, c: r.error(ST_EOF, b'\0', 0xfffffff0), nth=2, group=R,
  desc='STATUS_END_OF_FILE whose error ByteCount is 0xFFFFFFF0')
C('read_buffer_overflow_status', 'orc', READ, read_rep(status=ST_BUFFER_OVERFLOW), nth=2,
  group=R, desc='STATUS_BUFFER_OVERFLOW over a full READ body')
C('read_buffer_overflow_gt_asked', 'orc', READ,
  read_rep(status=ST_BUFFER_OVERFLOW, data=lambda a: b'\xee' * (a + 100)), nth=2, group=R,
  desc='STATUS_BUFFER_OVERFLOW with 100 bytes more than asked')
C('read_remaining_ffffffff', 'orc', READ, read_rep(remaining=0xffffffff), nth=2, group=R,
  desc='DataRemaining 0xFFFFFFFF')
C('read_big_gt_asked_by_1', 'orc', READ, read_rep(data=lambda a: b'\xee' * (a + 1)), nth=5,
  group=R, desc='asked 200000: 200001 sent')
C('read_reply_twice', 'orc', READ, nth=2, group=R,
  frame=lambda p, c, parts, i: ([nb(p), nb(p)], None),
  desc='the same READ reply sent twice')


# ── WRITE ───────────────────────────────────────────────────────────────────
def write_rep(count, remaining=0):
    def f(r, q, c):
        sent = q.g32(4)
        r.p32(4, count(sent) if callable(count) else count)
        r.p32(8, remaining)
    return f


W = 'write'
C('write_count_gt_sent', 'owc', WRITE, write_rep(lambda s: s * 2), nth=2, group=W,
  desc='sent 4096: Count 8192')
C('write_count_sent_plus1', 'owc', WRITE, write_rep(lambda s: s + 1), nth=2, group=W,
  desc='sent 4096: Count 4097')
C('write_count_7fffffff', 'owc', WRITE, write_rep(0x7fffffff), nth=2, group=W,
  desc='Count 0x7FFFFFFF')
C('write_count_80000000', 'owc', WRITE, write_rep(0x80000000), nth=2, group=W,
  desc='Count 0x80000000 (negative as an int)')
C('write_count_ffffffff', 'owc', WRITE, write_rep(0xffffffff), nth=2, group=W,
  desc='Count 0xFFFFFFFF (-1 as an int)')
C('write_count_fffffff3', 'owc', WRITE, write_rep(0xfffffff3), nth=2, group=W,
  desc='Count 0xFFFFFFF3 (-13, EACCES, as an int)')
C('write_count_0', 'owc', WRITE, write_rep(0), nth=2, group=W, desc='Count 0')
C('write_count_short', 'owc', WRITE, write_rep(lambda s: s // 2), nth=2, group=W,
  desc='Count half of what was sent (a legal short write)')
C('write_eof_status', 'owc', WRITE, lambda r, q, c: r.error(ST_EOF), nth=2, group=W,
  desc='STATUS_END_OF_FILE on a write')
C('write_eof_status_write_body', 'owc', WRITE, v_status(ST_EOF), nth=2, group=W,
  desc='STATUS_END_OF_FILE over a WRITE-shaped body')
C('write_remaining_ffffffff', 'owc', WRITE, write_rep(lambda s: s, 0xffffffff), nth=2, group=W,
  desc='Remaining 0xFFFFFFFF')


# ── QUERY_DIRECTORY ─────────────────────────────────────────────────────────
def qd(buf=None, offset=72, length=None, tail=b''):
    def f(r, q, c):
        b = default_dir() if buf is None else (buf() if callable(buf) else buf)
        r.body = bytearray(qdir_body(b, offset, length) + tail)
        r.status = ST_OK
    return f


D = 'query-directory'
C('qdir_outlen_gt_pdu', 'd', QUERY_DIRECTORY, qd(length=100000), group=D,
  desc='OutputBufferLength 100000 with ~500 bytes present')
C('qdir_outlen_ffffffff', 'd', QUERY_DIRECTORY, qd(length=0xffffffff), group=D,
  desc='OutputBufferLength 0xFFFFFFFF')
C('qdir_outlen_gt_pdu_stall', 'd', QUERY_DIRECTORY, qd(length=100000), group=D,
  frame=lambda p, c, parts, i: ([nb(p, 72 + 100000)], 'stall'),
  desc='OutputBufferLength 100000, NetBIOS length agrees, data never sent')
C('qdir_outlen_0_success', 'd', QUERY_DIRECTORY, qd(length=0), group=D,
  desc='STATUS_SUCCESS with OutputBufferLength 0')
C('qdir_outlen_lt_entry', 'd', QUERY_DIRECTORY, qd(length=40), group=D,
  desc='OutputBufferLength 40: less than one entry header')
C('qdir_outlen_cuts_name', 'd', QUERY_DIRECTORY, qd(length=82), group=D,
  desc='OutputBufferLength 82: the first name is cut')
for off in (0, 8, 64, 71, 73, 80, 0x1000, 0xffff):
    C('qdir_offset_%d' % off, 'd', QUERY_DIRECTORY, qd(offset=off), group=D,
      desc='OutputBufferOffset %d (72 is the valid one)' % off)
C('qdir_offset_80_padded', 'd', QUERY_DIRECTORY,
  lambda r, q, c: setattr(r, 'body', bytearray(struct.pack('<HHI', 9, 80, len(default_dir()))
                                               + b'\0' * 8 + default_dir())),
  group=D, desc='OutputBufferOffset 80 with 8 padding bytes (legal)')


def ents(*es):
    return lambda: dir_buffer([bytearray(e) for e in es])


for nxt, nm in ((1, '1'), (4, '4'), (8, '8'), (79, '79'), (0xffffffff, 'ffffffff'),
                (0x7fffffff, '7fffffff'), (0x80000000, '80000000'), (100000, 'past_end'),
                (88 + 80 - 4, 'cuts_next_header')):
    C('qdir_next_entry_' + nm, 'd', QUERY_DIRECTORY,
      qd(ents(dir_entry('aaaa', nxt=nxt), dir_entry('bbbb'), dir_entry('cccc'))), group=D,
      desc='first entry NextEntryOffset %s' % nm)
C('qdir_next_entry_overlap_chain', 'd', QUERY_DIRECTORY,
  qd(lambda: bytes(dir_entry('aaaa', nxt=8)) + b'\x08\0\0\0\0\0\0\0' * 2000), group=D,
  desc='2000 entries 8 bytes apart, each overlapping the next')
for nl, nm in ((0xffffffff, 'ffffffff'), (0x7fffffff, '7fffffff'), (0xfffffff0, 'fffffff0'),
               (1000, '1000_past_end'), (9, 'odd_9'), (0, '0'), (1, '1')):
    C('qdir_name_length_' + nm, 'd', QUERY_DIRECTORY,
      qd(ents(dir_entry('aaaa', name_len=nl), dir_entry('bbbb'))), group=D,
      desc='first entry FileNameLength %s' % nm)
C('qdir_last_name_length_past_end', 'd', QUERY_DIRECTORY,
  qd(ents(dir_entry('aaaa'), dir_entry('bbbb', name_len=64))), group=D,
  desc='last entry FileNameLength 64 with 8 bytes present')
C('qdir_name_lone_surrogates', 'd', QUERY_DIRECTORY,
  qd(ents(dir_entry('x', raw_name=b'\x00\xd8\x00\xd8\x00\xdc\x41\x00\x00\xdc'), dir_entry('b'))),
  group=D, desc='name made of unpaired UTF-16 surrogates')
C('qdir_name_embedded_nul', 'd', QUERY_DIRECTORY,
  qd(ents(dir_entry('ab\0cd'), dir_entry('b'))), group=D, desc='name with an embedded NUL')
C('qdir_name_path_traversal', 'd', QUERY_DIRECTORY,
  qd(ents(dir_entry('..\\..\\evil'), dir_entry('a/b'), dir_entry('\\\\x\\y'))), group=D,
  desc='names holding separators and ..')
C('qdir_name_30000_units', 'd', QUERY_DIRECTORY, qd(ents(dir_entry('A' * 30000), dir_entry('b'))),
  group=D, desc='one name of 30000 UTF-16 units')
C('qdir_name_all_ffff', 'd', QUERY_DIRECTORY,
  qd(ents(dir_entry('x', raw_name=b'\xff\xff' * 300), dir_entry('b'))), group=D,
  desc='name of 300 U+FFFF')
C('qdir_10000_entries', 'd', QUERY_DIRECTORY,
  qd(lambda: dir_buffer([dir_entry('f%05d' % i) for i in range(10000)])), group=D,
  desc='10000 entries in one reply (~1 MiB)')
for t, nm in ((0, '0'), (1, '1'), (0x7fffffffffffffff, '7fff'), (0xffffffffffffffff, 'ffff'),
              (0x8000000000000000, '8000'), (116444736000000000 - 1, 'just_before_1970')):
    C('qdir_times_' + nm, 'd', QUERY_DIRECTORY,
      qd(ents(dir_entry('aaaa', times=t), dir_entry('bbbb', times=t))), group=D,
      desc='entry FILETIMEs %s' % nm)
C('qdir_sizes_ffff', 'd', QUERY_DIRECTORY,
  qd(ents(dir_entry('aaaa', size=0xffffffffffffffff), dir_entry('b', size=1 << 63))), group=D,
  desc='EndOfFile 2^64-1 and 2^63')
C('qdir_no_more_files_with_data', 'd', QUERY_DIRECTORY,
  lambda r, q, c: r.error(ST_NO_MORE_FILES, bytes(default_dir()), len(default_dir())), nth=2,
  group=D, desc='STATUS_NO_MORE_FILES with a directory buffer as ErrorData')
C('qdir_buffer_overflow_status', 'd', QUERY_DIRECTORY,
  lambda r, q, c: (qd()(r, q, c), setattr(r, 'status', ST_BUFFER_OVERFLOW)), group=D,
  desc='STATUS_BUFFER_OVERFLOW over a directory buffer')


def h_qdir_endless(conn, q):
    conn.served += 1
    return Rep(q, ST_OK, qdir_body(default_dir()))


C('qdir_endless', 'd', group=D, handlers={QUERY_DIRECTORY: h_qdir_endless}, wall=12,
  desc='the server never says STATUS_NO_MORE_FILES')


# ── CREATE ──────────────────────────────────────────────────────────────────
def cr(off, length, extra=b''):
    def f(r, q, c):
        r.p32(80, off)
        r.p32(84, length)
        r.body += extra
    return f


def cctx(name=b'MxAc', data=b'\0' * 8, nxt=0, n_off=16, n_len=None, d_off=24, d_len=None):
    return struct.pack('<IHHHHI', nxt, n_off, len(name) if n_len is None else n_len, 0, d_off,
                       len(data) if d_len is None else d_len) + pad8(name) + data


K = 'create'
C('create_ctx_valid', 'oc', CREATE, cr(152, 32, cctx()), group=K,
  desc='a well-formed MxAc create context (control)')
C('create_ctx_offset_0', 'oc', CREATE, cr(0, 32, cctx()), group=K,
  desc='CreateContextsOffset 0 with length 32')
C('create_ctx_offset_64', 'oc', CREATE, cr(64, 32, cctx()), group=K,
  desc='CreateContextsOffset 64 (inside the reply)')
C('create_ctx_offset_past_end', 'oc', CREATE, cr(0x10000, 32, cctx()), group=K,
  desc='CreateContextsOffset 65536')
C('create_ctx_offset_ffffffff', 'oc', CREATE, cr(0xffffffff, 32, cctx()), group=K,
  desc='CreateContextsOffset 0xFFFFFFFF')
C('create_ctx_length_past_end', 'oc', CREATE, cr(152, 5000, cctx()), group=K,
  desc='CreateContextsLength 5000 with 32 present')
C('create_ctx_length_ffffffff', 'oc', CREATE, cr(152, 0xffffffff, cctx()), group=K,
  desc='CreateContextsLength 0xFFFFFFFF')
C('create_ctx_wrap', 'oc', CREATE, cr(0xffffff00, 0x200, cctx()), group=K,
  desc='offset + length wraps 32 bits')
C('create_ctx_next_backwards', 'oc', CREATE, cr(152, 32, cctx(nxt=0xffffffe0)), group=K,
  desc='context Next pointing backwards (circular)')
C('create_ctx_next_past_end', 'oc', CREATE, cr(152, 32, cctx(nxt=0x1000)), group=K,
  desc='context Next past the end')
C('create_ctx_name_past_end', 'oc', CREATE, cr(152, 32, cctx(n_off=0xfff0, n_len=0xffff)),
  group=K, desc='context NameOffset/Length out of range')
C('create_ctx_data_past_end', 'oc', CREATE, cr(152, 32, cctx(d_off=0xfff0, d_len=0xfffffff0)),
  group=K, desc='context DataOffset/Length out of range')
C('create_ctx_on_stat_compound', 's', CREATE, cr(152, 5000, cctx()), group=K,
  desc='CreateContextsLength past the element inside a compound reply')
for t, nm in ((0, '0'), (1, '1'), (0xffffffffffffffff, 'ffff'), (0x8000000000000000, '8000')):
    C('create_times_' + nm, 'oc', CREATE,
      lambda r, q, c, t=t: [r.p64(o, t) for o in (8, 16, 24, 32)], group=K,
      desc='CREATE reply FILETIMEs %s' % nm)
C('create_size_ffff', 'oc', CREATE, lambda r, q, c: (r.p64(40, -1), r.p64(48, -1)), group=K,
  desc='CREATE reply EndOfFile and AllocationSize 2^64-1')
C('create_oplock_ff', 'oc', CREATE, lambda r, q, c: r.p8(2, 0xff), group=K,
  desc='CREATE reply OplockLevel 0xFF (a lease) with no lease context')


# ── QUERY_INFO, for each class the client asks ──────────────────────────────
def is_class(t, k):
    return lambda c, q: q.body[2] == t and q.body[3] == k


def qi(mut):
    def f(r, q, c):
        buf = bytes(r.body[8:])
        r.body = bytearray(mut(buf))
    return f


QI_CLASSES = (('all_info', 1, 18, 's'), ('attribute_tag', 1, 35, 's'),
              ('fs_full_size', 2, 7, 'v'), ('all_info_fstat', 1, 18, 'ofc'))
QI_MUTS = (
    ('outlen_0', lambda b: qinfo_body(b'', length=0), 'OutputBufferLength 0, no data'),
    ('outlen_0_with_data', lambda b: qinfo_body(b, length=0), 'OutputBufferLength 0 with data'),
    ('outlen_1', lambda b: qinfo_body(b[:1]), '1 byte of output'),
    ('half', lambda b: qinfo_body(b[:len(b) // 2]), 'half of the structure'),
    ('minus_1', lambda b: qinfo_body(b[:-1]), 'one byte short'),
    ('outlen_gt_pdu', lambda b: qinfo_body(b, length=len(b) + 5000),
     'OutputBufferLength 5000 more than present'),
    ('outlen_ffffffff', lambda b: qinfo_body(b, length=0xffffffff), 'OutputBufferLength 2^32-1'),
    ('offset_0', lambda b: qinfo_body(b, offset=0), 'OutputBufferOffset 0'),
    ('offset_8', lambda b: qinfo_body(b, offset=8), 'OutputBufferOffset 8'),
    ('offset_64', lambda b: qinfo_body(b, offset=64), 'OutputBufferOffset 64'),
    ('offset_ffff', lambda b: qinfo_body(b, offset=0xffff), 'OutputBufferOffset 65535'),
    ('offset_80_padded', lambda b: struct.pack('<HHI', 9, 80, len(b)) + b'\0' * 8 + b,
     'OutputBufferOffset 80 with padding (legal)'),
    ('oversized_4096', lambda b: qinfo_body(b + b'\xaa' * 4096), '4096 extra bytes of output'),
    ('all_ff', lambda b: qinfo_body(b'\xff' * len(b)), 'structure filled with 0xFF'),
    ('all_00', lambda b: qinfo_body(b'\0' * len(b)), 'structure filled with zeros'),
)
for cn, t, k, ops in QI_CLASSES:
    for mn, mut, what in QI_MUTS:
        C('qinfo_%s_%s' % (cn, mn), ops, QUERY_INFO, qi(mut), nth=None, when=is_class(t, k),
          group='query-info', desc='%s: %s' % (cn, what))
for nl, nm in ((0xffffffff, 'ffffffff'), (0x7fffffff, '7fffffff'), (4000, '4000'), (7, 'odd_7')):
    C('qinfo_all_info_name_length_' + nm, 's', QUERY_INFO,
      lambda r, q, c, nl=nl: setattr(r, 'body', bytearray(qinfo_body(all_info(name_len=nl)))),
      nth=None, when=is_class(1, 18), group='query-info',
      desc='FILE_ALL_INFORMATION FileNameLength %s' % nm)
for tv, nm in ((0, '0'), (1, '1'), (0xffffffffffffffff, 'ffff'), (0x8000000000000000, '8000'),
               (116444736000000000 - 1, 'just_before_1970')):
    C('qinfo_all_info_times_' + nm, 's', QUERY_INFO,
      lambda r, q, c, tv=tv: setattr(r, 'body', bytearray(qinfo_body(all_info(times=tv)))),
      nth=None, when=is_class(1, 18), group='query-info',
      desc='FILE_ALL_INFORMATION FILETIMEs %s' % nm)
C('qinfo_all_info_size_ffff', 's', QUERY_INFO,
  lambda r, q, c: setattr(r, 'body', bytearray(qinfo_body(all_info(size=0xffffffffffffffff)))),
  nth=None, when=is_class(1, 18), group='query-info', desc='EndOfFile 2^64-1')
for vals, nm in (((0xffffffffffffffff, 0xffffffffffffffff, 0xffffffffffffffff, 0xffffffff,
                   0xffffffff), 'all_ff'), ((1, 1, 1, 0, 0), 'zero_units'),
                 ((1 << 63, 1 << 63, 1 << 63, 0x80000000, 0x80000000), 'overflow')):
    C('qinfo_fs_values_' + nm, 'v', QUERY_INFO,
      lambda r, q, c, vals=vals: setattr(r, 'body', bytearray(
          qinfo_body(struct.pack('<QQQII', *vals)))),
      nth=None, when=is_class(2, 7), group='query-info',
      desc='FS_FULL_SIZE_INFORMATION ' + nm.replace('_', ' '))
C('qinfo_buffer_overflow_status', 's', QUERY_INFO, v_status(ST_BUFFER_OVERFLOW), nth=None,
  when=is_class(1, 18), group='query-info',
  desc='STATUS_BUFFER_OVERFLOW over a full FILE_ALL_INFORMATION')
C('qinfo_buffer_overflow_short', 's', QUERY_INFO,
  lambda r, q, c: (qi(lambda b: qinfo_body(b[:40]))(r, q, c),
                   setattr(r, 'status', ST_BUFFER_OVERFLOW)),
  nth=None, when=is_class(1, 18), group='query-info',
  desc='STATUS_BUFFER_OVERFLOW with 40 bytes of FILE_ALL_INFORMATION')


# ── compound replies (stat = CREATE + QUERY_INFO + QUERY_INFO + CLOSE) ───────
def cmp_next(which, value):
    def f(payload, conn, parts, idx):
        p = bytearray(payload)
        off = sum(len(x) for x in parts[:which])
        v = value(p, parts, which) if callable(value) else value
        struct.pack_into('<I', p, off + 20, v & 0xffffffff)
        return [nb(bytes(p))], None
    return f


def alone(x):
    return nb(x[:20] + b'\0\0\0\0' + x[24:])


M = 'compound'
for which in (0, 1):
    for v, nm in ((0, '0'), (8, '8'), (32, '32'), (64, '64'), (65, '65'), (72, '72'),
                  (0x7fffffff, '7fffffff'), (0x80000000, '80000000'), (0xffffffff, 'ffffffff'),
                  (0xfffffff8, 'minus8'), (100000, 'past_end'),
                  (lambda p, parts, w: len(parts[w]) - 8, 'short_by_8'),
                  (lambda p, parts, w: len(parts[w]) + 8, 'long_by_8'),
                  (lambda p, parts, w: len(p) - sum(len(x) for x in parts[:w]), 'frame_end'),
                  (lambda p, parts, w: len(p) - sum(len(x) for x in parts[:w]) - 32,
                   'cuts_last_header')):
        C('compound_next%d_%s' % (which, nm), 's', CREATE, group=M,
          frame=cmp_next(which, v),
          desc='stat compound: NextCommand of element %d = %s' % (which, nm.replace('_', ' ')))
C('compound_last_next_nonzero', 's', CREATE, group=M, frame=cmp_next(3, 64),
  desc='stat compound: the last element has NextCommand 64')
C('compound_only_first', 's', CREATE, group=M,
  frame=lambda p, c, parts, i: ([alone(parts[0])], None),
  desc='stat compound: only the CREATE reply comes back')
C('compound_separate_frames', 's', CREATE, group=M,
  frame=lambda p, c, parts, i: ([alone(x) for x in parts], None),
  desc='stat compound answered as four separate frames (legal)')
C('compound_reversed', 's', CREATE, group=M,
  frame=lambda p, c, parts, i: ([alone(x) for x in reversed(parts)], None),
  desc='stat compound answered in reverse order, separate frames')
C('compound_swapped_in_chain', 's', CREATE, group=M,
  frame=lambda p, c, parts, i: ([nb(parts[1] + parts[0] + parts[2] + parts[3])], None),
  desc='stat compound with the first two replies swapped inside the chain')
C('compound_duplicate_element', 's', CREATE, group=M,
  frame=lambda p, c, parts, i: ([nb(parts[0] + parts[0] + parts[1] + parts[2] + parts[3])], None),
  desc='stat compound with the CREATE reply twice')
C('compound_extra_unknown_tail', 's', CREATE, group=M,
  frame=lambda p, c, parts, i: (
      [nb(b''.join(parts[:3]) + parts[3][:20] + struct.pack('<I', len(parts[3]) + 4) +
          parts[3][24:] + b'\0' * 4 + hdr(c, ECHO, 0x5555) + struct.pack('<HH', 4, 0))], None),
  desc='stat compound followed by a fifth reply nobody asked for')
C('compound_300_unknown', 'e', ECHO, group=M,
  frame=lambda p, c, parts, i: (
      [nb(b''.join(hdr(c, ECHO, 0x6000 + k, nxt=72) + struct.pack('<HH', 4, 0) + b'\0' * 4
                   for k in range(300)) + p)], None),
  desc='300 chained replies with unknown MessageIds, then the real one')
C('compound_first_fails_rest_ok', 's', CREATE, lambda r, q, c: r.error(ST_ACCESS_DENIED),
  group=M, desc='stat compound: CREATE fails, the rest reports success')
C('compound_qinfo_fails', 's', QUERY_INFO, lambda r, q, c: r.error(ST_ACCESS_DENIED),
  nth=1, group=M, desc='stat compound: the first QUERY_INFO fails')
C('compound_close_fails', 's', CLOSE, lambda r, q, c: r.error(ST_ACCESS_DENIED), group=M,
  desc='stat compound: only the CLOSE fails')
C('compound_readlink_ioctl_fails', 'k', IOCTL, lambda r, q, c: r.error(ST_ACCESS_DENIED),
  group=M, desc='readlink compound: the IOCTL fails')
C('compound_readlink_create_fails', 'k', CREATE, lambda r, q, c: r.error(ST_ACCESS_DENIED),
  group=M, desc='readlink compound: the CREATE fails')
C('compound_mkdir_close_fails', 'm', CLOSE, lambda r, q, c: r.error(ST_ACCESS_DENIED),
  group=M, desc='mkdir compound: the CLOSE fails')
C('compound_rename_setinfo_fails', 'n', SET_INFO, lambda r, q, c: r.error(ST_ACCESS_DENIED),
  group=M, desc='rename compound: the SET_INFO fails')
C('compound_pending_inside', 's', QUERY_INFO, v_errbody(ST_PENDING), nth=1, group=M,
  desc='stat compound with STATUS_PENDING on its second element')


# ── IOCTL: reparse point (readlink) ─────────────────────────────────────────
def io(out=None, **kw):
    def f(r, q, c):
        o = symlink_reparse() if out is None else out
        r.body = bytearray(ioctl_body(q.g32(4), o, **kw))
        r.status = ST_OK
    return f


I = 'ioctl-reparse'
RP = [('substitute_len_ffff', dict(s_len=0xffff)), ('substitute_off_ffff', dict(s_off=0xffff)),
      ('substitute_off_len_past', dict(s_off=8, s_len=64)),
      ('print_len_ffff', dict(p_len=0xffff)), ('print_off_ffff', dict(p_off=0xffff)),
      ('substitute_odd_len', dict(s_len=5)), ('data_len_0', dict(data_len=0)),
      ('data_len_ffff', dict(data_len=0xffff)), ('data_len_4', dict(data_len=4)),
      ('tag_mount_point', dict(tag=0xA0000003)), ('tag_unknown', dict(tag=0x12345678)),
      ('tag_0', dict(tag=0)), ('target_empty', dict(target='')),
      ('target_5000_chars', dict(target='B' * 5000)),
      ('target_4096_chars', dict(target='B' * 4096)),
      ('target_4095_chars', dict(target='B' * 4095)),
      ('target_2048_cjk', dict(target='\u6f22' * 2048)),
      ('target_16000_chars', dict(target='B' * 16000))]
for nm, kw in RP:
    C('readlink_' + nm, 'k', IOCTL, io(symlink_reparse(**kw)), group=I,
      desc='symlink reparse buffer: ' + nm.replace('_', ' '))
for n in (0, 1, 4, 7, 8, 12, 19, 20):
    C('readlink_buffer_cut_%d' % n, 'k', IOCTL, io(symlink_reparse()[:n]), group=I,
      desc='reparse buffer of %d bytes' % n)
C('readlink_surrogates', 'k', IOCTL,
  io(symlink_reparse('abcd').replace(u16('abcd'), b'\x00\xd8\x00\xd8\x41\x00\x00\xdc')),
  group=I, desc='symlink target of unpaired surrogates')
for nm, kw in (('out_offset_0', dict(out_off=0)), ('out_offset_64', dict(out_off=64)),
               ('out_offset_111', dict(out_off=111)),
               ('out_offset_ffffffff', dict(out_off=0xffffffff)),
               ('out_offset_past_end', dict(out_off=0x10000)),
               ('out_count_gt_pdu', dict(out_count=100000)),
               ('out_count_ffffffff', dict(out_count=0xffffffff)),
               ('out_count_0', dict(out_count=0)), ('out_count_4', dict(out_count=4)),
               ('in_count_ffffffff', dict(in_count=0xffffffff, in_off=112)),
               ('in_count_fffffff9_wrap', dict(in_count=0xfffffff9, in_off=112)),
               ('in_off_ffffffff', dict(in_count=8, in_off=0xffffffff)),
               ('in_count_8_before_out', dict(in_count=8, in_off=112, out_off=120, pre=b'I' * 8)),
               ('in_count_8_out_off_112', dict(in_count=8, in_off=112, out_off=112)),
               ('out_offset_120_padded', dict(out_off=120, pre=b'\0' * 8))):
    C('ioctl_' + nm, 'k', IOCTL, io(**kw), group=I, desc='IOCTL reply ' + nm.replace('_', ' '))
C('ioctl_ctlcode_mismatch', 'k', IOCTL, lambda r, q, c: r.p32(4, FSCTL_PIPE_TRANSCEIVE), group=I,
  desc='IOCTL reply with another CtlCode')
C('ioctl_buffer_overflow_status', 'k', IOCTL, v_status(ST_BUFFER_OVERFLOW), group=I,
  desc='STATUS_BUFFER_OVERFLOW over the reparse reply')

# ── share enumeration: DCE/RPC over the srvsvc pipe ─────────────────────────
S = 'share-enum'


def tr(out_fn, status=ST_OK, **kw):
    def f(r, q, c):
        ioff, icnt = q.g32(24), q.g32(28)
        cid = struct.unpack_from('<I', q.raw, ioff + 12)[0] if icnt >= 16 else 1
        r.body = bytearray(ioctl_body(q.g32(4), out_fn(cid), **kw))
        r.status = status
    return f


BIND = [('short_10', lambda cid: bind_ack(cid)[:10]), ('short_24', lambda cid: bind_ack(cid)[:24]),
        ('short_27', lambda cid: bind_ack(cid)[:27]),
        ('sec_addr_len_ffff', lambda cid: bind_ack(cid, sec_len=0xffff)),
        ('sec_addr_len_fff0', lambda cid: bind_ack(cid, sec_len=0xfff0)),
        ('nak', lambda cid: bind_ack(cid, ptype=13)),
        ('result_rejected', lambda cid: bind_ack(cid, result=2)),
        ('n_results_0', lambda cid: bind_ack(cid, n_results=0)),
        ('empty', lambda cid: b''),
        ('big_endian_drep', lambda cid: bind_ack(cid)[:4] + b'\0\0\0\0' + bind_ack(cid)[8:])]
for nm, fn in BIND:
    C('shareenum_bind_' + nm, 'E', IOCTL, tr(fn), nth=1, group=S,
      desc='BIND_ACK: ' + nm.replace('_', ' '))


def resp(stub=None, **kw):
    return lambda cid: dce_response(share_stub() if stub is None else stub, cid, **kw)


BIG = (('x' * 40, 0, 'y' * 40),) * 3
_st = share_stub()
ENUM = [
    ('frag_len_0', resp(frag_len=0)), ('frag_len_15', resp(frag_len=15)),
    ('frag_len_23', resp(frag_len=23)), ('frag_len_24', resp(frag_len=24)),
    ('frag_len_minus1', resp(frag_len=24 + len(_st) - 1)),
    ('frag_len_plus1', resp(frag_len=24 + len(_st) + 1)),
    ('frag_len_ffff', resp(frag_len=0xffff)),
    ('auth_len_ffff', resp(auth_len=0xffff)), ('auth_len_8', resp(auth_len=8)),
    ('version_4', lambda cid: b'\x04' + dce_response(_st, cid)[1:]),
    ('ptype_fault', lambda cid: dce_hdr(3, 32, cid) + struct.pack('<IHBBII', 4, 0, 0, 0, 0x1c010002, 0)),
    ('ptype_fault_short', lambda cid: dce_hdr(3, 16, cid)),
    ('ptype_fault_20', lambda cid: dce_hdr(3, 20, cid) + b'\0' * 4),
    ('ptype_99', resp(ptype=99)),
    ('big_endian_drep_le_data', resp(drep=b'\0\0\0\0')),
    ('header_cut_10', lambda cid: dce_response(_st, cid)[:10]),
    ('header_cut_16', lambda cid: dce_response(_st, cid)[:16]),
    ('stub_empty', resp(stub=b'')), ('stub_cut_4', resp(stub=_st[:4])),
    ('stub_cut_20', resp(stub=_st[:20])), ('stub_cut_24', resp(stub=_st[:24])),
    ('stub_cut_mid_array', resp(stub=_st[:40])),
    ('stub_cut_mid_string', resp(stub=_st[:70])),
    ('stub_cut_before_total', resp(stub=_st[:-12])),
    ('stub_cut_before_werror', resp(stub=_st[:-4])),
    ('level_mismatch', resp(stub=share_stub(level=2))),
    ('switch_mismatch', resp(stub=share_stub(sw=0))),
    ('count_ffffffff', resp(stub=share_stub(count=0xffffffff, max_count=0xffffffff))),
    ('count_40000000', resp(stub=share_stub(count=0x40000000, max_count=0x40000000))),
    ('count_1000_two_present', resp(stub=share_stub(count=1000, max_count=1000))),
    ('count_gt_max_count', resp(stub=share_stub(count=3, max_count=2))),
    ('count_0_buf_set', resp(stub=share_stub(count=0))),
    ('count_3_array_no_strings', resp(stub=share_stub(shares=BIG, strings=b''))),
    ('ctr_ref_0', resp(stub=share_stub(ctr_ref=0))), ('buf_ref_0', resp(stub=share_stub(buf_ref=0))),
    ('name_refs_null', resp(stub=share_stub(refs=((0, 0), (0, 0)), strings=b''))),
    ('first_name_ref_null', resp(stub=share_stub(shares=(('a', 0, 'b'),), refs=((0, 0x20004),),
                                                 strings=ndr_str('b')))),
    ('string_max_ffffffff', resp(stub=share_stub(strings=ndr_str('public', max_count=0xffffffff) +
                                                 ndr_str('x') * 3))),
    ('string_actual_ffffffff', resp(stub=share_stub(strings=ndr_str('public', max_count=0xffffffff,
                                                                    actual=0xffffffff)))),
    ('string_actual_gt_max', resp(stub=share_stub(strings=ndr_str('public', max_count=2, actual=7)))),
    ('string_actual_past_end', resp(stub=share_stub(strings=ndr_str('public', max_count=5000,
                                                                    actual=5000)))),
    ('string_offset_4', resp(stub=share_stub(strings=ndr_str('public', offset=4) + ndr_str('x') * 3))),
    ('string_not_terminated', resp(stub=share_stub(strings=ndr_str('public', nul=False) +
                                                   ndr_str('r', nul=False) + ndr_str('I', nul=False)
                                                   + ndr_str('s', nul=False)))),
    ('string_actual_0', resp(stub=share_stub(strings=ndr_str('', nul=False) * 4))),
    ('string_embedded_nul', resp(stub=share_stub(shares=(('pub\0lic', 0, 'r\0x'),)))),
    ('string_surrogates', resp(stub=share_stub(strings=(struct.pack('<III', 3, 0, 3) +
                                                        b'\x00\xd8\x00\xd8\x00\x00\0\0') * 4))),
    ('string_20000_chars', resp(stub=share_stub(shares=(('n' * 20000, 0, 'r' * 20000),)))),
    ('werror_5', resp(stub=share_stub(werror=5))),
    ('werror_ffffffff', resp(stub=share_stub(werror=0xffffffff))),
    ('total_ffffffff', resp(stub=share_stub(total=0xffffffff))),
    ('zero_shares', resp(stub=share_stub(shares=()))),
    ('1000_shares', resp(stub=share_stub(shares=tuple(('s%04d' % i, 0, 'r') for i in range(1000))))),
    ('trailing_data', lambda cid: dce_response(_st, cid) + b'\xaa' * 32),
    ('two_frags_mixed_byte_order', lambda cid: dce_response(_st[:40], cid, pfc=1) +
     dce_response(_st[40:], cid, pfc=2, drep=b'\0\0\0\0')),
    ('two_frags_ok', lambda cid: dce_response(_st[:40], cid, pfc=1) +
     dce_response(_st[40:], cid, pfc=2)),
    ('two_frags_second_len_short', lambda cid: dce_response(_st[:40], cid, pfc=1) +
     dce_response(_st[40:], cid, pfc=2, frag_len=20)),
    ('empty_output', lambda cid: b''),
]
for nm, fn in ENUM:
    C('shareenum_' + nm, 'E', IOCTL, tr(fn), nth=2, group=S,
      desc='NetrShareEnum reply: ' + nm.replace('_', ' '))


def first_frag_then_pipe(rest, first_pfc=1):
    def f(r, q, c):
        ioff = q.g32(24)
        cid = struct.unpack_from('<I', q.raw, ioff + 12)[0]
        c.pipe_data = rest(cid, _st)
        r.body = bytearray(ioctl_body(q.g32(4), dce_response(_st[:40], cid, pfc=first_pfc)))
        r.status = ST_BUFFER_OVERFLOW
    return f


C('shareenum_overflow_then_read_ok', 'E', IOCTL,
  first_frag_then_pipe(lambda cid, st: dce_response(st[40:], cid, pfc=2)), nth=2, group=S,
  desc='STATUS_BUFFER_OVERFLOW, the rest read from the pipe (legal)')
C('shareenum_overflow_then_read_nothing', 'E', IOCTL,
  first_frag_then_pipe(lambda cid, st: b''), nth=2, group=S,
  desc='STATUS_BUFFER_OVERFLOW, then the pipe READ returns 0 bytes')
C('shareenum_overflow_then_read_garbage', 'E', IOCTL,
  first_frag_then_pipe(lambda cid, st: b'\xaa' * 3000), nth=2, group=S,
  desc='STATUS_BUFFER_OVERFLOW, then the pipe READ returns garbage')


def h_pipe_endless(conn, q):
    # every READ on the pipe returns one more non-final fragment
    if not conn.ipc:
        return None
    frag = dce_response(b'\x41' * 4000, 2, pfc=0)
    conn.served += 1
    return Rep(q, ST_OK, struct.pack('<HBBIII', 17, 0x50, 0, len(frag), 0, 0) + frag)


C('shareenum_endless_fragments', 'E', IOCTL,
  first_frag_then_pipe(lambda cid, st: b'', first_pfc=0), nth=2, group=S, wall=15,
  handlers={READ: h_pipe_endless},
  desc='the response never has a last fragment: every pipe READ returns one more')


def h_pipe_read_overrun(conn, q):
    if not conn.ipc:
        return None
    asked = q.g32(4)
    frag = dce_response(b'\x41' * (asked + 4000), 2, pfc=2)
    return Rep(q, ST_OK, struct.pack('<HBBIII', 17, 0x50, 0, len(frag), 0, 0) + frag)


C('shareenum_pipe_read_gt_asked', 'E', IOCTL,
  first_frag_then_pipe(lambda cid, st: b'', first_pfc=0), nth=2, group=S,
  handlers={READ: h_pipe_read_overrun},
  desc='the pipe READ returns 4 kB more than the client asked for')
C('shareenum_create_fails', 'E', CREATE, lambda r, q, c: r.error(ST_ACCESS_DENIED), group=S,
  desc='opening the srvsvc pipe fails')
C('shareenum_request_fails', 'E', IOCTL, lambda r, q, c: r.error(ST_ACCESS_DENIED), nth=2,
  group=S, desc='the NetrShareEnum transceive fails')
C('shareenum_out_count_gt_pdu', 'E', IOCTL, tr(resp(), out_count=60000), nth=2, group=S,
  desc='transceive OutputCount 60000 with ~200 present')
C('shareenum_stall', 'E', IOCTL, nth=2, group=S, frame=lambda p, c, parts, i: ([], 'stall'),
  desc='the transceive is never answered')

# ── NEGOTIATE ───────────────────────────────────────────────────────────────
N = 'negotiate'


def ng(dialect=None, **kw):
    def f(r, q, c):
        r.body = bytearray(negotiate_body(c.dialect if dialect is None else dialect, **kw))
    return f


def ng_edit(*edits):
    def f(r, q, c):
        for off, fmt, val in edits:
            struct.pack_into(fmt, r.body, off, val)
    return f


C('neg_secbuf_offset_0', 'e', NEGOTIATE, ng_edit((56, '<H', 0)), group=N,
  desc='SecurityBufferOffset 0')
C('neg_secbuf_offset_64', 'e', NEGOTIATE, ng_edit((56, '<H', 64)), group=N,
  desc='SecurityBufferOffset 64 (inside the reply)')
C('neg_secbuf_offset_127', 'e', NEGOTIATE, ng_edit((56, '<H', 127)), group=N,
  desc='SecurityBufferOffset 127')
C('neg_secbuf_offset_ffff', 'e', NEGOTIATE, ng_edit((56, '<H', 0xffff)), group=N,
  desc='SecurityBufferOffset 65535')
C('neg_secbuf_length_ffff', 'e', NEGOTIATE, ng_edit((58, '<H', 0xffff)), group=N,
  desc='SecurityBufferLength 65535')
C('neg_secbuf_length_plus1', 'e', NEGOTIATE,
  lambda r, q, c: r.p16(58, struct.unpack_from('<H', r.body, 58)[0] + 1), group=N,
  desc='SecurityBufferLength one more than present')
C('neg_secbuf_length_0', 'e', NEGOTIATE, ng_edit((58, '<H', 0)), group=N,
  desc='SecurityBufferLength 0 with a blob present')
C('neg_secbuf_none', 'e', NEGOTIATE, ng(sec=b''), group=N, desc='no security blob at all')
C('neg_secbuf_promised_never_sent', 'e', NEGOTIATE, ng_edit((56, '<H', 200), (58, '<H', 4000)),
  group=N, frame=lambda p, c, parts, i: ([nb(p, 4300)], 'stall'),
  desc='security buffer of 4000 bytes promised by every length, never sent')
C('neg_secbuf_offset_past_311', 'e', NEGOTIATE, ng_edit((56, '<H', 0x3000), (58, '<H', 16)),
  ver=0x0311, group=N,
  desc='3.1.1: SecurityBufferOffset 0x3000 in a larger declared frame',
  frame=lambda p, c, parts, i: ([nb(p + b'\0' * 0x3100)], None))
for d in (0, 0x0200, 0x02ff, 0x0500, 0xffff, 0x0100):
    C('neg_dialect_%04x' % d, 'e', NEGOTIATE, ng_edit((4, '<H', d)), group=N,
      desc='DialectRevision 0x%04x (never offered)' % d)
C('neg_dialect_311_when_210_only', 'e', NEGOTIATE, ng(dialect=0x0311), ver=0x0210, group=N,
  desc='server picks 3.1.1 when the client offered 2.1 only')
for v, nm in ((0, '0'), (1, '1'), (0xffffffff, 'ffffffff'), (0x80000000, '80000000'),
              (65536, '65536'), (100, '100')):
    C('neg_max_sizes_' + nm, 'dsorwc', NEGOTIATE,
      ng_edit((28, '<I', v), (32, '<I', v), (36, '<I', v)), group=N,
      desc='MaxTransact/Read/WriteSize %s, then a normal session' % nm)
C('neg_max_read_1_write_ffffffff', 'orwc', NEGOTIATE,
  ng_edit((32, '<I', 1), (36, '<I', 0xffffffff)), group=N,
  desc='MaxReadSize 1, MaxWriteSize 2^32-1')
C('neg_signing_required', 'e', NEGOTIATE, ng_edit((2, '<H', 3)), group=N,
  desc='SecurityMode signing required (the server then never signs)')
C('neg_caps_ffffffff', 'dsorwc', NEGOTIATE, ng_edit((24, '<I', 0xffffffff)), group=N,
  desc='Capabilities 0xFFFFFFFF')

_si = spnego_init()
SP = [('truncated_1', _si[:1]), ('truncated_half', _si[:len(_si) // 2]),
      ('len_84_ffffffff', b'\x60\x84\xff\xff\xff\xff' + _si[2:]),
      ('len_indefinite', b'\x60\x80' + _si[2:]),
      ('len_89', b'\x60\x89' + b'\xff' * 9 + _si[2:]),
      ('inner_len_past_end', _si[:11] + b'\x7f' + _si[12:]),
      ('nested_2000', b'\x60\x82\x10\x00' + OID_SPNEGO + b'\xa0\x82\x0f\x00' + b'\x30\x80' * 2000),
      ('nested_seq_len_chain',
       b''.join(b'\x30\x82' + struct.pack('>H', 4000 - 4 * k) for k in range(1000))),
      ('oid_len_ff', b'\x60\x20\x06\x81\xff' + b'\x2b' * 29),
      ('all_ff_200', b'\xff' * 200), ('all_00_200', b'\0' * 200), ('all_30_200', b'\x30' * 200),
      ('raw_ntlmssp', ntlm_challenge()),
      ('mechlist_empty', der(0x60, OID_SPNEGO + der(0xa0, der(0x30, der(0xa0, der(0x30, b'')))))),
      ('mechlist_500_oids',
       der(0x60, OID_SPNEGO + der(0xa0, der(0x30, der(0xa0, der(0x30, OID_NTLMSSP * 500)))))),
      ('mech_krb5_only',
       der(0x60, OID_SPNEGO + der(0xa0, der(0x30, der(0xa0, der(
           0x30, bytes.fromhex('06092a864886f712010202')))))))]
for nm, blob in SP:
    C('neg_spnego_' + nm, 'e', NEGOTIATE, ng(sec=blob), group='spnego',
      desc='negotiate SPNEGO blob: ' + nm.replace('_', ' '))


# 3.1.1 negotiate contexts
def nctx(contexts=None, count=None, offset=None, raw=None, cut=None):
    def f(r, q, c):
        body = bytearray(negotiate_body(0x0311, contexts=contexts))
        if raw is not None:
            base = struct.unpack_from('<I', body, 60)[0] - 64
            body = body[:base] + raw
        if count is not None:
            struct.pack_into('<H', body, 6, count)
        if offset is not None:
            struct.pack_into('<I', body, 60, offset(len(body)) if callable(offset) else offset)
        if cut is not None:
            body = body[:len(body) - cut]
        r.body = body
    return f


PRE = default_contexts()[0]
ENC = default_contexts()[1]
X = 'negotiate-contexts'
NC = [
    ('valid', dict()),
    ('count_0', dict(count=0)), ('count_1000_two_present', dict(count=1000)),
    ('count_ffff', dict(count=0xffff)),
    ('offset_0', dict(offset=0)), ('offset_64', dict(offset=64)), ('offset_127', dict(offset=127)),
    ('offset_at_end', dict(offset=lambda n: 64 + n)),
    ('offset_end_minus_4', dict(offset=lambda n: 60 + n)),
    ('offset_past_end', dict(offset=0x10000)), ('offset_ffffffff', dict(offset=0xffffffff)),
    ('offset_80000000', dict(offset=0x80000000)),
    ('datalen_ffff', dict(raw=struct.pack('<HHI', 1, 0xffff, 0) + PRE[1])),
    ('datalen_past_end_by_1', dict(raw=struct.pack('<HHI', 2, 5, 0) + ENC[1])),
    ('header_cut_4', dict(raw=struct.pack('<HH', 1, 38))),
    ('last_cut_2', dict(cut=2)),
    ('no_preauth', dict(contexts=[ENC])), ('no_contexts', dict(contexts=[], count=0)),
    ('preauth_twice', dict(contexts=[PRE, PRE, ENC])),
    ('preauth_hash_count_0', dict(contexts=[(1, struct.pack('<HHH', 0, 32, 1) + b'S' * 32), ENC])),
    ('preauth_hash_count_ffff',
     dict(contexts=[(1, struct.pack('<HHH', 0xffff, 32, 1) + b'S' * 32), ENC])),
    ('preauth_salt_len_ffff',
     dict(contexts=[(1, struct.pack('<HHH', 1, 0xffff, 1) + b'S' * 32), ENC])),
    ('preauth_hash_unknown',
     dict(contexts=[(1, struct.pack('<HHH', 1, 32, 0x99) + b'S' * 32), ENC])),
    ('preauth_empty', dict(contexts=[(1, b''), ENC])),
    ('cipher_count_0', dict(contexts=[PRE, (2, struct.pack('<HH', 0, 2))])),
    ('cipher_count_ffff', dict(contexts=[PRE, (2, struct.pack('<HH', 0xffff, 2))])),
    ('cipher_unknown', dict(contexts=[PRE, (2, struct.pack('<HH', 1, 0x9999))])),
    ('cipher_none_0', dict(contexts=[PRE, (2, struct.pack('<HH', 1, 0))])),
    ('cipher_ccm', dict(contexts=[PRE, (2, struct.pack('<HH', 1, 1))])),
    ('cipher_aes256gcm', dict(contexts=[PRE, (2, struct.pack('<HH', 1, 4))])),
    ('cipher_ctx_2_bytes', dict(contexts=[PRE, (2, b'\x01\0')])),
    ('cipher_ctx_empty', dict(contexts=[PRE, (2, b'')])),
    ('unknown_type_99', dict(contexts=[PRE, ENC, (99, b'\0' * 8)])),
    ('signing_ctx_garbage', dict(contexts=[PRE, ENC, (8, b'\xff' * 3)])),
    ('compression_ctx_garbage', dict(contexts=[PRE, ENC, (3, b'\xff' * 5)])),
    ('netname_ctx_60000', dict(contexts=[PRE, ENC, (5, b'A\0' * 30000)])),
    ('rdma_transport_ctx_empty', dict(contexts=[PRE, ENC, (6, b''), (7, b'')])),
    ('500_contexts', dict(contexts=[PRE] + [(8, b'\x01\0\x01\0')] * 499)),
]
for nm, kw in NC:
    C('negctx_' + nm, 'dsorwc', NEGOTIATE, nctx(**kw), ver=0x0311, group=X,
      desc='3.1.1 negotiate contexts: ' + nm.replace('_', ' '))

# ── SESSION_SETUP ───────────────────────────────────────────────────────────
A = 'session-setup'


def ss(tok, offset=72, length=None, status=ST_MORE, flags=0):
    def f(r, q, c):
        t = tok() if callable(tok) else tok
        r.body = bytearray(struct.pack('<HHHH', 9, flags, offset,
                                       len(t) if length is None else length) + t)
        r.status = status
    return f


def av(*pairs, eol=True):
    out = b''
    for k, v in pairs:
        out += struct.pack('<HH', k, len(v) if not isinstance(v, tuple) else v[0])
        out += v if not isinstance(v, tuple) else v[1]
    return out + (struct.pack('<HH', 0, 0) if eol else b'')


_c = ntlm_challenge()
CH = [('cut_%d' % n, _c[:n]) for n in (4, 8, 11, 12, 20, 24, 32, 40, 44, 48, 56, 60)] + [
    ('empty', b''),
    ('wrong_signature', ntlm_challenge(sig=b'NTLMSSQ\0')),
    ('type_1', ntlm_challenge(mtype=1)), ('type_3', ntlm_challenge(mtype=3)),
    ('type_99', ntlm_challenge(mtype=99)), ('type_0', ntlm_challenge(mtype=0)),
    ('target_name_len_ffff', ntlm_challenge(t_len=0xffff)),
    ('target_name_off_ffffffff', ntlm_challenge(t_off=0xffffffff)),
    ('target_name_off_past_end', ntlm_challenge(t_off=5000)),
    ('target_name_off_0', ntlm_challenge(t_off=0)),
    ('target_name_odd_len', ntlm_challenge(t_len=5)),
    ('target_info_len_ffff', ntlm_challenge(i_len=0xffff)),
    ('target_info_off_ffffffff', ntlm_challenge(i_off=0xffffffff)),
    ('target_info_off_80000000', ntlm_challenge(i_off=0x80000000)),
    ('target_info_off_past_end', ntlm_challenge(i_off=5000)),
    ('target_info_len_past_by_1', ntlm_challenge(i_len=struct.unpack_from('<H', _c, 40)[0] + 1)),
    ('target_info_off_0', ntlm_challenge(i_off=0)),
    ('target_info_len_0', ntlm_challenge(i_len=0)),
    ('target_info_len_1', ntlm_challenge(i_len=1)), ('target_info_len_3', ntlm_challenge(i_len=3)),
    ('av_len_past_end', ntlm_challenge(info=av((2, (0xfff0, b'AB'))))),
    ('av_len_ffff_only', ntlm_challenge(info=struct.pack('<HH', 2, 0xffff))),
    ('av_no_eol', ntlm_challenge(info=av((2, u16('D')), (1, u16('C')), eol=False))),
    ('av_header_cut', ntlm_challenge(info=av((2, u16('D')), eol=False) + b'\x01\0\x08')),
    ('av_timestamp_short', ntlm_challenge(info=av((7, b'\x01\x02')))),
    ('av_timestamp_long', ntlm_challenge(info=av((7, b'\x01' * 64)))),
    ('av_flags_short', ntlm_challenge(info=av((6, b'\x02')))),
    ('av_1000_pairs', ntlm_challenge(info=av(*(((2, u16('D')),) * 1000)))),
    ('av_60000_bytes', ntlm_challenge(info=av((2, b'D\0' * 30000)))),
    ('av_unknown_ids', ntlm_challenge(info=av((0x99, b'x' * 10), (0xffff, b'y' * 4)))),
    ('av_channel_bindings_short', ntlm_challenge(info=av((10, b'\0' * 3)))),
    ('av_target_name_ffff_len', ntlm_challenge(info=av((9, (0xffff, b'cifs'))))),
    ('flags_0', ntlm_challenge(flags=0)), ('flags_ffffffff', ntlm_challenge(flags=0xffffffff)),
    ('flags_no_target_info', ntlm_challenge(flags=0xE20A8215)),
    ('flags_oem_no_unicode', ntlm_challenge(flags=0xE28A8216)),
    ('target_30000_chars', ntlm_challenge(target='T' * 30000)),
    ('payload_offsets_48', ntlm_challenge(t_off=48, i_off=48)),
]
for nm, blob in CH:
    C('ntlm_challenge_' + nm, 'e', SESSION_SETUP, ss(blob), group='ntlmssp',
      desc='NTLMSSP challenge: ' + nm.replace('_', ' '))
for nm, blob in (('valid', spnego_challenge(_c)),
                 ('token_len_past_end', spnego_challenge(_c)[:-40]),
                 ('octet_len_84', der(0xa1, der(0x30, der(0xa2, b'\x04\x84\x7f\xff\xff\xff' + _c)))),
                 ('no_token', der(0xa1, der(0x30, der(0xa0, bytes([0x0a, 1, 1]))))),
                 ('neg_state_reject', der(0xa1, der(0x30, der(0xa0, bytes([0x0a, 1, 2]))))),
                 ('token_cut_20', spnego_challenge(_c[:20])),
                 ('nested_1000', b'\xa1\x82\x10\x00' + b'\x30\x80' * 1000),
                 ('mic_huge', der(0xa1, der(0x30, der(0xa2, der(0x04, _c)) +
                                            der(0xa3, der(0x04, b'M' * 5000)))))):
    C('ss_spnego_' + nm, 'e', SESSION_SETUP, ss(blob), group='spnego',
      desc='SPNEGO-wrapped challenge: ' + nm.replace('_', ' '))
C('ss_secbuf_offset_0', 'e', SESSION_SETUP, ss(_c, offset=0), group=A,
  desc='SecurityBufferOffset 0')
C('ss_secbuf_offset_64', 'e', SESSION_SETUP, ss(_c, offset=64), group=A,
  desc='SecurityBufferOffset 64')
C('ss_secbuf_offset_ffff', 'e', SESSION_SETUP, ss(_c, offset=0xffff), group=A,
  desc='SecurityBufferOffset 65535')
C('ss_secbuf_length_ffff', 'e', SESSION_SETUP, ss(_c, length=0xffff), group=A,
  desc='SecurityBufferLength 65535')
C('ss_secbuf_length_plus1', 'e', SESSION_SETUP, ss(_c, length=len(_c) + 1), group=A,
  desc='SecurityBufferLength one more than present')
C('ss_secbuf_length_0_more_processing', 'e', SESSION_SETUP, ss(_c, length=0),
  group=A, desc='MORE_PROCESSING_REQUIRED with SecurityBufferLength 0')
C('ss_secbuf_offset_80_padded', 'e', SESSION_SETUP,
  ss(b'\0' * 8 + _c, offset=80, length=len(_c)), group=A,
  desc='SecurityBufferOffset 80 with padding (legal)')
C('ss_success_at_first_leg', 'dsorc', SESSION_SETUP, ss(b'', status=ST_OK), group=A,
  desc='STATUS_SUCCESS at the first leg, no challenge')
C('ss_success_at_first_leg_311', 'dsorc', SESSION_SETUP, ss(b'', status=ST_OK), ver=0x0311,
  group=A, desc='STATUS_SUCCESS at the first leg on 3.1.1 (no session key)')
C('ss_final_with_blob', 'e', SESSION_SETUP, ss(spnego_challenge(_c), status=ST_OK),
  nth=2, group=A, desc='final leg carries another challenge blob')
C('ss_final_signed_garbage_210', 'e', SESSION_SETUP,
  lambda r, q, c: r.hdr.update(flags=9, sig=b'\xaa' * 16), nth=2, group=A,
  desc='final leg flagged SIGNED with a garbage signature (2.1)')
C('ss_final_signed_garbage_311', 'e', SESSION_SETUP,
  lambda r, q, c: r.hdr.update(flags=9, sig=b'\xaa' * 16), nth=2, ver=0x0311, group=A,
  desc='final leg flagged SIGNED with a garbage signature (3.1.1)')
for fl, nm in ((1, 'guest'), (2, 'null'), (4, 'encrypt_data'), (0xffff, 'ffff')):
    C('ss_session_flags_' + nm, 'dsorc', SESSION_SETUP,
      lambda r, q, c, fl=fl: r.p16(2, fl), nth=2, group=A,
      desc='final leg SessionFlags %s (2.1)' % nm)
    C('ss_session_flags_%s_311' % nm, 'dsorc', SESSION_SETUP,
      lambda r, q, c, fl=fl: r.p16(2, fl), nth=2, ver=0x0311, group=A,
      desc='final leg SessionFlags %s (3.1.1)' % nm)
C('ss_session_id_0', 'dsorc', SESSION_SETUP, lambda r, q, c: setattr(c, 'sess', 0), group=A,
  desc='SessionId 0')
C('ss_session_id_changes', 'dsorc', SESSION_SETUP,
  lambda r, q, c: setattr(c, 'sess', 0x9999), nth=2, group=A,
  desc='the SessionId changes between the two legs')


def h_ss_endless(conn, q):
    conn.served += 1
    tok = ntlm_challenge()
    return Rep(q, ST_MORE, struct.pack('<HHHH', 9, 0, 72, len(tok)) + tok)


C('ss_more_processing_forever', 'e', group=A, handlers={SESSION_SETUP: h_ss_endless}, wall=12,
  desc='every leg is answered MORE_PROCESSING_REQUIRED with a new challenge')

# ── TREE_CONNECT ────────────────────────────────────────────────────────────
T = 'tree-connect'
for st, nm in ((0, '0'), (3, 'print'), (0xff, 'ff')):
    C('tree_share_type_' + nm, 'dsorc', TREE_CONNECT, lambda r, q, c, st=st: r.p8(2, st), group=T,
      desc='ShareType %s' % nm)
for ver in (0x0210, 0x0302, 0x0311):
    C('tree_flags_encrypt_data_%04x' % ver, 'dsorc', TREE_CONNECT,
      lambda r, q, c: r.p32(4, 0x8008), ver=ver, group=T,
      desc='ShareFlags ENCRYPT_DATA on %04x (the server then sends plaintext)' % ver)
C('tree_flags_ffffffff', 'dsorc', TREE_CONNECT, lambda r, q, c: r.p32(4, 0xffffffff), group=T,
  desc='ShareFlags 0xFFFFFFFF')
C('tree_caps_ffffffff', 'dsorc', TREE_CONNECT, lambda r, q, c: r.p32(8, 0xffffffff), group=T,
  desc='share Capabilities 0xFFFFFFFF')
C('tree_id_0', 'dsorc', TREE_CONNECT, lambda r, q, c: r.hdr.update(tree=0), group=T,
  desc='TreeId 0')
C('tree_id_ffffffff', 'dsorc', TREE_CONNECT, lambda r, q, c: r.hdr.update(tree=0xffffffff),
  group=T, desc='TreeId 0xFFFFFFFF')


# ── silence and close at each step ──────────────────────────────────────────
def slow(p, c, parts, i):
    data = nb(p)
    step = max(1, len(data) // 40)
    out = []
    for k in range(0, len(data), step):
        out += [data[k:k + step], 0.005]
    return out, None


for cmd, ops, nth in ((NEGOTIATE, 'e', 1), (SESSION_SETUP, 'e', 1), (SESSION_SETUP, 'e', 2),
                      (TREE_CONNECT, 'e', 1), (CREATE, 'oc', 1), (READ, 'orc', 2),
                      (WRITE, 'owc', 2), (QUERY_DIRECTORY, 'd', 1), (CLOSE, 'oc', 1),
                      (IOCTL, 'k', 1), (QUERY_INFO, 's', 1), (ECHO, 'e', 1)):
    n = CMDNAME[cmd] + ('%d' % nth if cmd == SESSION_SETUP else '')
    C('silence_at_' + n, ops, cmd, nth=nth, group='silence',
      frame=lambda p, c, parts, i: ([], 'stall'), desc='no answer to ' + n)
    C('close_at_' + n, ops, cmd, nth=nth, group='silence',
      frame=lambda p, c, parts, i: ([], 'close'),
      desc='connection closed instead of answering ' + n)
    C('close_mid_reply_' + n, ops, cmd, nth=nth, group='silence',
      frame=lambda p, c, parts, i: ([nb(p)[:4 + 64 + 3]], 'close'),
      desc='EOF 3 bytes into the body of the %s reply' % n)
    C('slow_bytes_' + n, ops, cmd, nth=nth, group='silence', frame=slow,
      desc='the %s reply arrives in ~40 small segments (legal)' % n)
