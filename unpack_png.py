#!/usr/bin/env python3
"""Standalone decoder for B01FILE4 RGB PNGs.

Usage:
    python unpack_png.py part_000001.png                 # restores with original name
    python unpack_png.py part_000001.png --out my.mcpack
    python unpack_png.py <folder with part_*.png>        # for multi-PNG sets

Needs only Python 3 + Pillow (pip install pillow). Verifies SHA-256.
"""
import argparse, bz2, hashlib, lzma, struct, sys, zlib
from pathlib import Path
from PIL import Image


def read_shard(p):
    with Image.open(p) as im:
        if im.mode != "RGB":
            raise ValueError(f"{p.name}: must be the original RGB PNG (not converted/recompressed)")
        raw = im.tobytes()
    if raw[:4] != b"B01P":
        raise ValueError(f"{p.name}: not a B01FILE4 PNG")
    i, count, n = struct.unpack(">IIQ", raw[4:20])
    return i, count, raw[20:20 + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path); ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    files = sorted(a.path.glob("part_*.png")) if a.path.is_dir() else [a.path]
    if not files: sys.exit("ERROR: no PNG files found")
    chunks, count = {}, None
    for f in files:
        i, c, d = read_shard(f); chunks[i] = d; count = c
    if sorted(chunks) != list(range(count)):
        sys.exit(f"ERROR: need all {count} PNG parts, found {len(chunks)}")
    blob = b"".join(chunks[i] for i in range(count))

    if blob[:4] != b"B01X" or blob[4] != 4: sys.exit("ERROR: bad container")
    method = blob[5]
    osz, psz, nl = struct.unpack(">QQH", blob[6:24]); h = blob[24:56]
    name = blob[56:56 + nl].decode(); payload = blob[56 + nl:56 + nl + psz]
    data = {0: lambda x: x, 1: zlib.decompress, 2: bz2.decompress, 3: lzma.decompress}[method](payload)
    if len(data) != osz or hashlib.sha256(data).digest() != h:
        sys.exit("ERROR: SHA-256 verification FAILED (PNG was modified or corrupted)")
    out = a.out or a.path.parent / Path(name).name if not a.path.is_dir() else (a.out or a.path / Path(name).name)
    Path(out).write_bytes(data)
    print(f"OK: {out} | {len(data):,} bytes | SHA-256 verified")


if __name__ == "__main__":
    main()
