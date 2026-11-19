#!/usr/bin/env python3
"""B01FILE3: split any file into lossless black/white PNG shards and restore it."""
import argparse, hashlib, json, math, sys, zlib
from pathlib import Path
import numpy as np
from PIL import Image

MAGIC=b"B01S"; VERSION=3; HS=49
DEFAULT_WIDTH=4096; DEFAULT_MAX_PIXELS=16_777_216

def sha(b): return hashlib.sha256(b).hexdigest()

def write_png(data,path,width,max_pixels):
    bits=np.unpackbits(np.frombuffer(data,dtype=np.uint8),bitorder="big")
    height=max(1,math.ceil(bits.size/width))
    if width*height>max_pixels: raise ValueError("Shard exceeds max-pixels limit")
    a=np.zeros(width*height,dtype=np.uint8); a[:bits.size]=bits
    Image.fromarray((a.reshape(height,width)*255).astype(np.uint8),"L").convert("1").save(path,format="PNG",optimize=True,compress_level=9)
    return height

def read_bits(path):
    with Image.open(path) as im:
        if im.format!="PNG": raise ValueError(f"{path.name}: original PNG required")
        return (np.asarray(im.convert("L"),dtype=np.uint8).reshape(-1)>=128).astype(np.uint8)

def get_bytes(bits,n):
    if n*8>bits.size: raise ValueError("Incomplete PNG shard")
    return np.packbits(bits[:n*8],bitorder="big").tobytes()

def shard_header(i,count,data):
    return MAGIC+bytes([VERSION])+i.to_bytes(4,"big")+count.to_bytes(4,"big")+len(data).to_bytes(4,"big")+hashlib.sha256(data).digest()

def parse_shard(path,expected,count):
    b=read_bits(path); h=get_bytes(b,HS)
    if h[:4]!=MAGIC or h[4]!=VERSION: raise ValueError(f"{path.name}: invalid shard header")
    i=int.from_bytes(h[5:9],"big"); c=int.from_bytes(h[9:13],"big"); n=int.from_bytes(h[13:17],"big")
    if i!=expected or c!=count: raise ValueError(f"{path.name}: shard order/count mismatch")
    raw=get_bytes(b,HS+n); data=raw[HS:]
    if hashlib.sha256(data).digest()!=h[17:49]: raise ValueError(f"{path.name}: shard checksum failed")
    return data

def pack(src,out,width,max_pixels):
    if not src.is_file(): raise FileNotFoundError(src)
    if width<1 or max_pixels<width: raise ValueError("Invalid width/max-pixels")
    original=src.read_bytes(); comp=zlib.compress(original,9)
    if len(comp)<len(original): stored,method=comp,"zlib"
    else: stored,method=original,"none"
    cap=max_pixels//8-HS
    if cap<1: raise ValueError("max-pixels too small")
    chunks=[stored[i:i+cap] for i in range(0,len(stored),cap)] or [b""]
    out.mkdir(parents=True,exist_ok=True); entries=[]
    for i,ch in enumerate(chunks):
        name=f"part_{i+1:06d}.png"; height=write_png(shard_header(i,len(chunks),ch)+ch,out/name,width,max_pixels)
        entries.append({"file":name,"index":i,"stored_bytes":len(ch),"sha256":sha(ch),"width":width,"height":height})
    manifest={"format":"B01FILE3","version":3,"original_filename":src.name,"original_size":len(original),"original_sha256":sha(original),"compression":method,"stored_size":len(stored),"shard_count":len(chunks),"shards":entries,"pixel_mapping":{"black":0,"white":1,"bit_order":"MSB-first"}}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    total=sum((out/e["file"]).stat().st_size for e in entries)
    print(f"PACK SUCCESS | original={len(original):,} bytes | compression={method} | stored={len(stored):,} bytes | shards={len(chunks)} | PNG total={total:,} bytes | folder={out}")

def load_set(folder):
    m=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if m.get("format")!="B01FILE3" or m.get("version")!=3: raise ValueError("Invalid B01FILE3 manifest")
    entries=m.get("shards",[])
    if len(entries)!=m.get("shard_count"): raise ValueError("Manifest shard count mismatch")
    chunks=[]
    for i,e in enumerate(entries):
        name=e["file"]
        if Path(name).name!=name: raise ValueError("Unsafe shard filename")
        d=parse_shard(folder/name,i,len(entries))
        if len(d)!=e["stored_bytes"] or sha(d)!=e["sha256"]: raise ValueError(f"{name}: manifest checksum mismatch")
        chunks.append(d)
    stored=b"".join(chunks)
    if len(stored)!=m["stored_size"]: raise ValueError("Stored payload size mismatch")
    if m["compression"]=="zlib":
        obj=zlib.decompressobj(); original=obj.decompress(stored)+obj.flush()
        if not obj.eof or obj.unused_data: raise ValueError("Invalid compressed stream")
    elif m["compression"]=="none": original=stored
    else: raise ValueError("Unknown compression method")
    if len(original)!=m["original_size"] or sha(original)!=m["original_sha256"]: raise ValueError("Original size/SHA-256 verification failed")
    return m,original

def verify(folder):
    m,d=load_set(folder); print(f"VERIFY PASS | {m['original_filename']} | {len(d):,} bytes | {m['shard_count']} shards | SHA-256 {sha(d)}")

def unpack(folder,out):
    m,d=load_set(folder); name=Path(m["original_filename"]).name or "recovered.bin"
    dest=out or folder/f"recovered_{name}"; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(d)
    print(f"UNPACK SUCCESS | {dest} | {len(d):,} bytes | integrity PASS")

def main():
    p=argparse.ArgumentParser(description="Split any file into binary-noise PNGs and recover it exactly")
    s=p.add_subparsers(dest="cmd",required=True)
    a=s.add_parser("pack"); a.add_argument("input",type=Path); a.add_argument("--out",type=Path); a.add_argument("--width",type=int,default=DEFAULT_WIDTH); a.add_argument("--max-pixels",type=int,default=DEFAULT_MAX_PIXELS)
    a=s.add_parser("unpack"); a.add_argument("folder",type=Path); a.add_argument("--out",type=Path)
    a=s.add_parser("verify"); a.add_argument("folder",type=Path)
    x=p.parse_args()
    try:
        if x.cmd=="pack": pack(x.input,x.out or x.input.with_name(x.input.name+".b01set"),x.width,x.max_pixels)
        elif x.cmd=="unpack": unpack(x.folder,x.out)
        else: verify(x.folder)
    except Exception as e: print("ERROR:",e,file=sys.stderr); return 1
    return 0
if __name__=="__main__": raise SystemExit(main())
