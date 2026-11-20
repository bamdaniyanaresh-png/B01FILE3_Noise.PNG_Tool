#!/usr/bin/env python3
"""B01FILE4 - lossless smallest-size packer.

Default output is a single compact .b01 file (best size). Optional --png mode
stores the same bytes as 24-bit RGB PNG shards (3 bytes/pixel, 24x denser than
the 1-bit B01FILE3) for services that only accept images.

Pipeline: [folder -> tar] -> try raw / zlib-9 / bz2-9 / several LZMA(xz) setups
-> keep the smallest -> container with SHA-256 -> (optional) RGB PNG shards.
Unpack always verifies SHA-256, so output is byte-identical to the original.
"""
import argparse, bz2, hashlib, io, lzma, math, struct, sys, tarfile, zlib
from pathlib import Path

MAGIC = b"B01X"; VER = 4
METHODS = {0: "raw", 1: "zlib", 2: "bz2", 3: "lzma"}
PNG_MAGIC = b"B01P"


def sha(b): return hashlib.sha256(b).digest()


# ---------------------------------------------------------------- compression
def lzma_raw(data, preset, lc=3, lp=0, pb=2, nice=273, dict_size=None):
    filt = [{"id": lzma.FILTER_LZMA2, "preset": preset | lzma.PRESET_EXTREME,
             "lc": lc, "lp": lp, "pb": pb, "nice_len": nice,
             "dict_size": dict_size or max(1 << 16, min(1 << 30, len(data)))}]
    return lzma.compress(data, format=lzma.FORMAT_XZ, check=lzma.CHECK_NONE, filters=filt)


def best_compress(data, fast=False, log=print):
    cands = [(0, "raw", data)]
    if fast:
        cands.append((3, "xz-6", lzma_raw(data, 6)))
    else:
        cands.append((1, "zlib-9", zlib.compress(data, 9)))
        cands.append((2, "bz2-9", bz2.compress(data, 9)))
        # different LZMA literal/position settings suit different data
        for lc, lp, pb in [(3, 0, 2), (4, 0, 0), (0, 0, 0), (8, 0, 0), (2, 0, 2), (3, 2, 2)]:
            if lc + lp > 4 and (lc, lp) != (8, 0): continue
            try: cands.append((3, f"xz-9e lc{lc} lp{lp} pb{pb}", lzma_raw(data, 9, lc, lp, pb)))
            except lzma.LZMAError: pass
    best = min(cands, key=lambda c: len(c[2]))
    for m, n, d in cands:
        log(f"  try {n:<22} {len(d):>14,} bytes{'  <== best' if d is best[2] else ''}")
    return best[0], best[2]


def decompress(method, payload):
    if method == 0: return payload
    if method == 1: return zlib.decompress(payload)
    if method == 2: return bz2.decompress(payload)
    if method == 3: return lzma.decompress(payload)
    raise ValueError("unknown method")


# ---------------------------------------------------------------- container
def read_input(src):
    if src.is_dir():
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t: t.add(src, arcname=src.name)
        return src.name + ".tar", buf.getvalue()
    return src.name, src.read_bytes()


def build_container(name, original, fast, log):
    method, payload = best_compress(original, fast, log)
    nb = name.encode()
    head = MAGIC + bytes([VER, method]) + struct.pack(">QQH", len(original), len(payload), len(nb)) + sha(original) + nb
    return head + payload, method


def parse_container(blob):
    if blob[:4] != MAGIC or blob[4] != VER: raise ValueError("not a B01FILE4 container")
    method = blob[5]
    osz, psz, nl = struct.unpack(">QQH", blob[6:24]); h = blob[24:56]
    name = blob[56:56 + nl].decode(); payload = blob[56 + nl:56 + nl + psz]
    if len(payload) != psz: raise ValueError("truncated data")
    data = decompress(method, payload)
    if len(data) != osz or sha(data) != h: raise ValueError("SHA-256 verification FAILED")
    return name, data, method


# ---------------------------------------------------------------- PNG (RGB) mode
def blob_to_pngs(blob, out_dir, width, max_pixels, np, Image):
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = (max_pixels * 3) - 20                    # bytes per shard (20-byte shard header)
    chunks = [blob[i:i + cap] for i in range(0, len(blob), cap)] or [b""]
    total = 0
    for i, ch in enumerate(chunks):
        raw = PNG_MAGIC + struct.pack(">IIQ", i, len(chunks), len(ch)) + ch
        pad = (-len(raw)) % (width * 3)
        arr = np.frombuffer(raw + b"\0" * pad, dtype=np.uint8).reshape(-1, width, 3)
        p = out_dir / f"part_{i + 1:06d}.png"
        # payload is already compressed -> deflate cannot help; level 0 = fastest, ~0 overhead
        Image.fromarray(arr, "RGB").save(p, format="PNG", compress_level=0)
        total += p.stat().st_size
    return len(chunks), total


def pngs_to_blob(folder, np, Image):
    parts = [folder] if folder.is_file() else sorted(folder.glob("part_*.png"))
    chunks = {}; count = None
    for p in parts:
        with Image.open(p) as im:
            if im.mode != "RGB": raise ValueError(f"{p.name}: RGB PNG required (don't convert/recompress)")
            raw = np.asarray(im, dtype=np.uint8).tobytes()
        if raw[:4] != PNG_MAGIC: raise ValueError(f"{p.name}: bad shard")
        i, c, n = struct.unpack(">IIQ", raw[4:20]); count = c; chunks[i] = raw[20:20 + n]
    if count is None or sorted(chunks) != list(range(count)): raise ValueError("missing shard(s)")
    return b"".join(chunks[i] for i in range(count))


# ---------------------------------------------------------------- commands
def cmd_pack(a):
    name, original = read_input(a.input)
    print(f"input: {name} | {len(original):,} bytes")
    blob, method = build_container(name, original, a.fast, print)
    if a.png:
        import numpy as np; from PIL import Image
        out = a.out or a.input.with_name(a.input.name + ".b01png")
        n, total = blob_to_pngs(blob, out, a.width, a.max_pixels, np, Image)
        print(f"PACK OK (PNG) | {len(original):,} -> {total:,} bytes in {n} PNG(s) | {total / max(1, len(original)) * 100:.2f}% | {out}")
    else:
        out = a.out or a.input.with_name(a.input.name + ".b01")
        out.write_bytes(blob)
        print(f"PACK OK | {len(original):,} -> {len(blob):,} bytes | {len(blob) / max(1, len(original)) * 100:.2f}% | method={METHODS[method]} | {out}")


def load(path):
    if path.is_dir() or path.suffix.lower() == ".png":
        import numpy as np; from PIL import Image
        blob = pngs_to_blob(path, np, Image)
    else: blob = path.read_bytes()
    return parse_container(blob)


def cmd_verify(a):
    name, data, m = load(a.path); print(f"VERIFY PASS | {name} | {len(data):,} bytes | method={METHODS[m]} | SHA-256 OK")


def cmd_unpack(a):
    name, data, m = load(a.path)
    dest = a.out or a.path.with_name("restored_" + name)
    dest.write_bytes(data); print(f"UNPACK OK | {dest} | {len(data):,} bytes | SHA-256 OK")


def main():
    p = argparse.ArgumentParser(description="Lossless smallest-size packer (file/folder -> .b01 or RGB PNG set)")
    s = p.add_subparsers(dest="cmd", required=True)
    a = s.add_parser("pack"); a.add_argument("input", type=Path); a.add_argument("--out", type=Path)
    a.add_argument("--png", action="store_true", help="write RGB PNG shards instead of a .b01 file")
    a.add_argument("--fast", action="store_true"); a.add_argument("--width", type=int, default=4096)
    a.add_argument("--max-pixels", type=int, default=16_777_216)
    a = s.add_parser("unpack"); a.add_argument("path", type=Path); a.add_argument("--out", type=Path)
    a = s.add_parser("verify"); a.add_argument("path", type=Path)
    x = p.parse_args()
    try: {"pack": cmd_pack, "unpack": cmd_unpack, "verify": cmd_verify}[x.cmd](x)
    except Exception as e: print("ERROR:", e, file=sys.stderr); return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
