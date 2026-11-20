# B01FILE4 — Lossless Binary PNG Packer

Kisi bhi file ya folder ko **lossless** chhota karke ya to ek compact `.b01` file mein, ya **24-bit RGB binary-noise PNG** mein badalta hai, aur phir **bilkul original** wapas nikalta hai. Har restore par SHA-256 check hota hai, ek byte bhi badla to error aata hai.

## Package mein kya hai

| File | Kaam |
|---|---|
| `b01file4.py` | Poora tool: `pack` (convert), `unpack` (restore), `verify` |
| `unpack_png.py` | Chhota standalone decoder: sirf PNG se restore (numpy nahi chahiye) |
| `requirements.txt` | `pillow`, `numpy` |
| `README.md` | Yeh guide |

## Install

Python 3.8+ chahiye.

```bash
# PC / Linux / Mac
python -m pip install pillow numpy

# Android (Termux)
pkg update && pkg install python
python -m pip install pillow numpy
```

> `.b01` mode (bina PNG) sirf Python se chalta hai, Pillow/numpy ki zaroorat sirf PNG mode mein hai.
> `unpack_png.py` ko sirf `pillow` chahiye.

## Convert (pack)

```bash
# 1) Binary PNG mein convert
python b01file4.py pack "myfile.mcpack" --png
#    -> myfile.mcpack.b01png/part_000001.png  (badi file ho to part_000002.png, ... )

# Output folder ka naam khud chuno
python b01file4.py pack "myfile.mcpack" --png --out "my_png_set"

# 2) Sabse chhota size (PNG nahi, ek .b01 file)
python b01file4.py pack "myfile.mcpack"

# 3) Folder pack karna (andar se tar ban jaata hai)
python b01file4.py pack "MyFolder" --png
```

Options:

| Option | Matlab |
|---|---|
| `--png` | PNG shards banao (RGB, 3 bytes/pixel) |
| `--out PATH` | Output file/folder ka naam |
| `--fast` | Jaldi chalao (kam compression try karta hai), badi files ke liye |
| `--width 4096` | PNG ki chaudai (pixels) |
| `--max-pixels 16777216` | Ek PNG mein max pixels. Chhota rakho to zyada, chhoti PNGs banengi |

## Restore (unpack)

```bash
# Single PNG se
python b01file4.py unpack part_000001.png

# Multi-PNG set (folder) se
python b01file4.py unpack my_png_set

# .b01 file se
python b01file4.py unpack myfile.mcpack.b01

# Naam/jagah khud chuno
python b01file4.py unpack part_000001.png --out "myfile.mcpack"
```

Bina kuch badle seedha PNG se restore (standalone decoder):

```bash
python unpack_png.py part_000001.png
python unpack_png.py my_png_set            # multi-PNG set
python unpack_png.py part_000001.png --out "myfile.mcpack"
```
Yeh original naam se file wapas bana deta hai.

## Check karna (verify)

```bash
python b01file4.py verify my_png_set
python b01file4.py verify part_000001.png
```
`VERIFY PASS ... SHA-256 OK` aaye to data bilkul sahi hai.

## Yeh kaise kaam karta hai

1. File (ya folder ka tar) padhta hai.
2. Teen tarah try karta hai: raw, zlib-9, bz2-9, aur LZMA/xz ki kai settings. **Jo sabse chhota ho wahi rakhta hai.**
3. Ek container banata hai: `B01X` header + original size + SHA-256 + original naam + compressed data.
4. `--png` ho to container ko RGB pixels mein likhta hai (1 pixel = 3 bytes) aur PNG shards mein baant deta hai. Har shard ka apna chhota header (`B01P`, index, count, length) hota hai.

PNG mein compression level 0 rakha hai, kyunki data pehle hi compress ho chuka hota hai. Deflate ab kuch nahi bacha sakta.

## Zaroori baatein

- **PNG ko chhedo mat:** resize, crop, screenshot, JPEG mein convert, ya aisi service jo images recompress karti hai (WhatsApp photo mode, social media), isse data kharab ho jaata hai. File/document ke roop mein bhejo.
- **Saare parts saath rakho:** multi-PNG set mein ek bhi `part_XXXXXX.png` kho gayi to restore nahi hoga. Parity/backup nahi hai.
- **Yeh encryption nahi hai.** Koi bhi script se data nikal sakta hai. Private data ke liye pehle khud encrypt karo.
- **Size ki seema:** MP4, JPEG, ZIP, APK, encrypted jaisi pehle se compressed files ko koi bhi lossless tool bahut chhota nahi kar sakta, thoda hi bachta hai (aksar 0-10%). Text, logs, JSON, code, CSV mein bahut bachat hoti hai (70-90% tak).
- **RAM:** poori file ek baar memory mein padhi jaati hai. Bahut badi (GBs) files ke liye kaafi RAM chahiye.
- **Hamesha pehle check karo:** source delete karne se pehle `pack` -> `unpack` -> hash compare karke dekho.
- Script (`b01file4.py` ya `unpack_png.py`) ko PNG ke saath hi rakho, restore ke liye zaroori hai.

## Test results (is tool se)

| Data | Original | Output | Bacha |
|---|---|---|---|
| MP4 video (9.9 MB) | 9,892,375 B | 9,873,579 B (.b01) | 0.19% |
| Log text (11 MB) | 11,046,096 B | 818,188 B (.b01) | 92.6% |
| `.mcpack` shader (1.3 MB) | 1,330,234 B | 1,217,060 B (PNG) | 8.5% |

## Technical format (agar khud decoder likhna ho)

**PNG shard** (RGB, 3 bytes/pixel, row-major, aakhir mein zero padding):
```
"B01P" | index u32 | count u32 | length u64 | data[length]      (big-endian)
```
Saare shards ka `data` index order mein jodo -> **container**:
```
"B01X" | ver=4 | method u8 | orig_size u64 | payload_size u64 | name_len u16
       | sha256(original) [32] | name | payload
```
`method`: 0 = raw, 1 = zlib, 2 = bz2, 3 = lzma(xz). Payload ko us method se decompress karo, SHA-256 match karo.
