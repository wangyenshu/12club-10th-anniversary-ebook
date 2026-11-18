#!/usr/bin/env python3
"""Extract the files packed inside an iebook (iebook 超级精灵, Guangzhou Feitian Media)
e-magazine .exe: config.xml, main.swf, every page SWF / JPG / PNG and the MP3s.

    python3 extract_iebook.py 10th_Anniversary.exe out/

How the player stores them (iebook player 6.0.0.4, Delphi + F-IN-BOX):
the files are an overlay appended after the PE image, starting with the magic "IERD".

    header   "IERD" u32 version, u32 52, u32 window width, u32 window height,
             u32 0, u32 0, u32 n + n ASCII chars (hex key/hash), u32 0
    entries  repeated until the end of the file:
             u32  id
             u32  n,  n ASCII hex chars  -> file name, XOR-ed with KEY
             u64  flags
             6    ASCII hex chars        -> the file's first 3 bytes, XOR-ed with KEY
             u32  size, size bytes       -> the rest of the file, unchanged
    trailer  u32 overlay offset, u32 0, u32 total exe size   (last 12 bytes)

Stripping the first three bytes is what hides the "CWS"/"FWS" SWF signature, the JPEG
"\\xff\\xd8\\xff" and the "<?x" of the XML. KEY is the same 8 bytes for both the name
and the header bytes; it is found from the first entry (always config.xml) when it
differs from the default one below.
"""
import os
import struct
import sys

DEFAULT_KEY = bytes.fromhex("b209aa55936d8447")
FIRST_NAME = b"config.xml"


def trailer(data):
    """(overlay offset, end of entries) from the 12-byte trailer, or None."""
    if len(data) >= 12:
        start, zero, total = struct.unpack_from("<III", data, len(data) - 12)
        if zero == 0 and total == len(data) and data[start:start + 4] == b"IERD":
            return start, len(data) - 12
    return None


def find_overlay(data):
    """Offset of the "IERD" overlay: trailer, else right after the last PE section, else a search."""
    t = trailer(data)
    if t:
        return t[0]
    try:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        nsec = struct.unpack_from("<H", data, pe + 6)[0]
        opt = struct.unpack_from("<H", data, pe + 20)[0]
        end = 0
        for i in range(nsec):
            sec = pe + 24 + opt + 40 * i
            size, ptr = struct.unpack_from("<II", data, sec + 16)
            end = max(end, ptr + size)
        if data[end:end + 4] == b"IERD":
            return end
    except struct.error:
        pass
    pos = data.find(b"IERD")
    if pos < 0:
        raise ValueError("no iebook overlay (IERD) in this file")
    return pos


def xor(buf, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(buf))


class Reader:
    def __init__(self, data, pos):
        self.data, self.pos = data, pos

    def u32(self):
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.data, self.pos)[0]
        self.pos += 8
        return v

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("truncated entry at offset %d" % self.pos)
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v


def parse(data):
    """Return (header dict, list of (name, bytes))."""
    t = trailer(data)
    end = t[1] if t else len(data)
    r = Reader(data[:end], find_overlay(data))
    if r.take(4) != b"IERD":
        raise ValueError("bad magic")
    header = {"version": r.u32(), "header_size": r.u32(),
              "window_width": r.u32(), "window_height": r.u32()}
    r.u32(), r.u32()
    header["hash"] = r.take(r.u32()).decode("ascii")
    r.u32()

    key = DEFAULT_KEY
    entries = []
    while r.pos < end:
        entry_id = r.u32()
        enc_name = bytes.fromhex(r.take(r.u32()).decode("ascii"))
        flags = r.u64()
        enc_head = bytes.fromhex(r.take(6).decode("ascii"))
        body = r.take(r.u32())
        if not entries and xor(enc_name, key) != FIRST_NAME and len(enc_name) == len(FIRST_NAME):
            key = xor(enc_name[:8], FIRST_NAME[:8])   # known plaintext: first entry is config.xml
        name = xor(enc_name, key).decode("utf-8", "replace")
        entries.append({"id": entry_id, "name": name, "flags": flags,
                        "data": xor(enc_head, key) + body})
    header["key"] = key.hex()
    return header, entries


def safe_name(name):
    name = name.replace("\\", "/").split("/")[-1]
    if name in ("", ".", ".."):
        raise ValueError("bad file name %r" % name)
    return name


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__.split("\n\n")[1].strip())
    exe, out = argv[1], argv[2]
    with open(exe, "rb") as f:
        data = f.read()
    header, entries = parse(data)
    os.makedirs(out, exist_ok=True)
    files = {}                                   # some files are packed twice, byte for byte
    for e in entries:
        name = safe_name(e["name"])
        if name in files and files[name] != e["data"]:
            sys.exit("%s is packed twice with different contents" % name)
        files[name] = e["data"]
    for name, data in files.items():
        with open(os.path.join(out, name), "wb") as f:
            f.write(data)
    kinds = {}
    for name in files:
        ext = os.path.splitext(name)[1].lower() or "(none)"
        kinds[ext] = kinds.get(ext, 0) + 1
    print("iebook v%d, window %dx%d, key %s" % (header["version"], header["window_width"],
                                                 header["window_height"], header["key"]))
    print("%d entries, %d files -> %s  (%s)" % (len(entries), len(files), out,
                                                ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items()))))


if __name__ == "__main__":
    main(sys.argv)
