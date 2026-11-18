#!/usr/bin/env python3
"""Patch the extracted iebook engine (main.swf) for Ruffle.

    python3 patch_main_swf.py book/main.swf

The engine keeps bookmarks, drawings and settings in a SharedObject whose name contains
characters Flash forbids there (~ % & \\ ; : " ' , < > ? # and space), so Ruffle refuses
it ("SharedObject::get_local: Invalid character in name") and nothing is saved.
This prepends one DoAction tag that wraps SharedObject.getLocal and replaces those
characters with "_" before calling the original. Nothing else in the file changes.
The patch is idempotent: a file that already has it is left alone.
"""
import struct
import sys
import zlib

MARKER = "__ruffleGetLocal"
BAD = "~%&\\;:\"',<>?# "


class Asm:
    """Just enough of an AVM1 assembler for the wrapper below."""

    def __init__(self):
        self.code = bytearray()
        self.fixups = []          # (offset of the s16 operand, label)
        self.labels = {}

    def op(self, code, payload=b""):
        if code >= 0x80:
            self.code += bytes([code]) + struct.pack("<H", len(payload)) + payload
        else:
            self.code.append(code)

    def push(self, *values):
        out = bytearray()
        for v in values:
            if isinstance(v, str):
                out += b"\x00" + v.encode("utf-8") + b"\x00"
            elif isinstance(v, bool):
                out += b"\x05" + bytes([v])
            elif isinstance(v, int):
                out += b"\x07" + struct.pack("<i", v)
            else:
                raise TypeError(v)
        self.op(0x96, bytes(out))

    def branch(self, code, label):            # 0x99 jump, 0x9D if
        self.op(code, b"\0\0")
        self.fixups.append((len(self.code) - 2, label))

    def label(self, name):
        self.labels[name] = len(self.code)

    def bytes(self):
        for pos, name in self.fixups:
            struct.pack_into("<h", self.code, pos, self.labels[name] - (pos + 2))
        return bytes(self.code)


GET_VAR, SET_VAR, DEFINE_LOCAL, GET_MEMBER, SET_MEMBER = 0x1C, 0x1D, 0x3C, 0x4E, 0x4F
CALL_METHOD, RETURN, ADD2, LESS2, NOT, INCREMENT, END = 0x52, 0x3E, 0x47, 0x48, 0x12, 0x50, 0x00
JUMP, IF = 0x99, 0x9D


def wrapper_body():
    """function (name, path, secure): sanitize name, call the original getLocal."""
    a = Asm()
    a.push("bad", BAD); a.op(DEFINE_LOCAL)
    a.push("out", ""); a.op(DEFINE_LOCAL)
    a.push("i", 0); a.op(DEFINE_LOCAL)
    a.label("loop")
    a.push("i"); a.op(GET_VAR)                                  # i < String(name).length
    a.push("name"); a.op(GET_VAR); a.push("length"); a.op(GET_MEMBER)
    a.op(LESS2); a.op(NOT); a.branch(IF, "done")
    a.push("c", "i"); a.op(GET_VAR); a.push(1)                  # c = name.charAt(i)
    a.push("name"); a.op(GET_VAR); a.push("charAt"); a.op(CALL_METHOD); a.op(DEFINE_LOCAL)
    a.push("out", "out"); a.op(GET_VAR)                          # out += bad.indexOf(c) < 0 ? c : "_"
    a.push("c"); a.op(GET_VAR); a.push(1)
    a.push("bad"); a.op(GET_VAR); a.push("indexOf"); a.op(CALL_METHOD)
    a.push(0); a.op(LESS2); a.op(NOT); a.branch(IF, "bad")
    a.push("c"); a.op(GET_VAR); a.branch(JUMP, "join")
    a.label("bad")
    a.push("_")
    a.label("join")
    a.op(ADD2); a.op(SET_VAR)
    a.push("i", "i"); a.op(GET_VAR); a.op(INCREMENT); a.op(SET_VAR)
    a.branch(JUMP, "loop")
    a.label("done")
    a.push("secure"); a.op(GET_VAR); a.push("path"); a.op(GET_VAR)   # args pushed last-first
    a.push("out"); a.op(GET_VAR); a.push(3)
    a.push("_global"); a.op(GET_VAR); a.push("SharedObject"); a.op(GET_MEMBER)
    a.push(MARKER); a.op(CALL_METHOD); a.op(RETURN)
    return a.bytes()


def do_action():
    body = wrapper_body()
    params = ["name", "path", "secure"]
    define = b"\x00" + struct.pack("<H", len(params)) + b"".join(p.encode() + b"\0" for p in params)
    define += struct.pack("<H", len(body))
    a = Asm()
    # if (SharedObject.__ruffleGetLocal == undefined) {
    a.push("_global"); a.op(GET_VAR); a.push("SharedObject"); a.op(GET_MEMBER)
    a.push(MARKER); a.op(GET_MEMBER); a.op(0x44)                  # typeof
    a.push("undefined"); a.op(0x49); a.op(NOT); a.branch(IF, "end")   # equals2
    #   SharedObject.__ruffleGetLocal = SharedObject.getLocal
    a.push("_global"); a.op(GET_VAR); a.push("SharedObject"); a.op(GET_MEMBER); a.push(MARKER)
    a.push("_global"); a.op(GET_VAR); a.push("SharedObject"); a.op(GET_MEMBER)
    a.push("getLocal"); a.op(GET_MEMBER); a.op(SET_MEMBER)
    #   SharedObject.getLocal = function (name, path, secure) { ... }
    a.push("_global"); a.op(GET_VAR); a.push("SharedObject"); a.op(GET_MEMBER); a.push("getLocal")
    a.op(0x9B, define)
    a.code += body
    a.op(SET_MEMBER)
    a.label("end")
    a.op(END)
    return a.bytes()


def tag(code, payload):
    if len(payload) < 63:
        return struct.pack("<H", code << 6 | len(payload)) + payload
    return struct.pack("<HI", code << 6 | 63, len(payload)) + payload


def patch(data):
    sig, version = data[:3], data[3]
    if sig == b"CWS":
        body = zlib.decompress(data[8:])
    elif sig == b"FWS":
        body = data[8:]
    else:
        raise ValueError("not an uncompressed or zlib SWF")
    if MARKER.encode() in body:
        return None
    nbits = body[0] >> 3
    header_len = (5 + 4 * nbits + 7) // 8 + 4             # RECT + frame rate + frame count
    p = header_len
    # keep FileAttributes / SetBackgroundColor / Metadata first, then our DoAction
    while True:
        h = struct.unpack_from("<H", body, p)[0]
        code, ln = h >> 6, h & 63
        size = 2
        if ln == 63:
            ln = struct.unpack_from("<I", body, p + 2)[0]
            size = 6
        if code not in (69, 9, 77, 24, 64, 65, 253):      # attributes, bg, metadata, protect, script limits
            break
        p += size + ln
    new_body = body[:p] + tag(12, do_action()) + body[p:]
    out = b"FWS" + bytes([version]) + struct.pack("<I", 8 + len(new_body)) + new_body
    if sig == b"CWS":
        out = b"CWS" + out[3:8] + zlib.compress(new_body, 9)
    return out


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__.split("\n\n")[1].strip())
    with open(argv[1], "rb") as f:
        data = f.read()
    out = patch(data)
    if out is None:
        print("%s: already patched" % argv[1])
        return
    with open(argv[1], "wb") as f:
        f.write(out)
    print("%s: SharedObject.getLocal wrapper added (%d -> %d bytes)" % (argv[1], len(data), len(out)))


if __name__ == "__main__":
    main(sys.argv)
