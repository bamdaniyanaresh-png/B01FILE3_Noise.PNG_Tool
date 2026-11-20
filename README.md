# B01FILE4 --- Lossless Binary PNG Packer

Converts any file or folder into either a compact `.b01` file or a
**24-bit RGB binary-noise PNG** using lossless compression, then
restores it to its **exact original form**. Every restoration is
verified using SHA-256. If even a single byte has changed, verification
fails with an error.

## Package Contents

  -----------------------------------------------------------------------
  File                                Description
  ----------------------------------- -----------------------------------
  `b01file4.py`                       Complete tool: `pack` (convert),
                                      `unpack` (restore), and `verify`

  `unpack_png.py`                     Lightweight standalone decoder that
                                      restores files directly from PNG
                                      images (does not require NumPy)

  `requirements.txt`                  Dependencies: `pillow`, `numpy`

  `README.md`                         This guide
  -----------------------------------------------------------------------

## Installation

Python 3.8+ is required.

``` bash
# PC / Linux / macOS
python -m pip install pillow numpy

# Android (Termux)
pkg update && pkg install python
python -m pip install pillow numpy
```

> `.b01` mode (without PNG) works using Python alone. Pillow and NumPy
> are only required for PNG mode.
>
> `unpack_png.py` requires only Pillow.

## Convert (Pack)

``` bash
# 1) Convert into binary PNG format
python b01file4.py pack "myfile.mcpack" --png
#    -> myfile.mcpack.b01png/part_000001.png
#       (additional parts are created for larger files)

# Choose a custom output folder name
python b01file4.py pack "myfile.mcpack" --png --out "my_png_set"

# 2) Smallest output size (no PNG, creates a single .b01 file)
python b01file4.py pack "myfile.mcpack"

# 3) Pack an entire folder (automatically converted into a TAR archive)
python b01file4.py pack "MyFolder" --png
```

### Options

  -----------------------------------------------------------------------
  Option                              Description
  ----------------------------------- -----------------------------------
  `--png`                             Generate PNG shards (RGB, 3 bytes
                                      per pixel)

  `--out PATH`                        Specify the output file or folder
                                      name

  `--fast`                            Faster processing with fewer
                                      compression attempts; useful for
                                      large files

  `--width 4096`                      Set the PNG width in pixels

  `--max-pixels 16777216`             Maximum pixels per PNG. Lower
                                      values produce more, smaller PNG
                                      files
  -----------------------------------------------------------------------

## Restore (Unpack)

``` bash
# Restore from a single PNG
python b01file4.py unpack part_000001.png

# Restore from a multi-PNG set (folder)
python b01file4.py unpack my_png_set

# Restore from a .b01 file
python b01file4.py unpack myfile.mcpack.b01

# Specify a custom output filename or location
python b01file4.py unpack part_000001.png --out "myfile.mcpack"
```

### Restore Directly from PNG Using the Standalone Decoder

``` bash
python unpack_png.py part_000001.png

python unpack_png.py my_png_set
# Restores a multi-PNG set

python unpack_png.py part_000001.png --out "myfile.mcpack"
```

The standalone decoder automatically restores the file using its
original filename when no custom output name is specified.

## Verify Data Integrity

``` bash
python b01file4.py verify my_png_set

python b01file4.py verify part_000001.png
```

If the output displays `VERIFY PASS ... SHA-256 OK`, the data has been
verified successfully.

## How It Works

1.  Reads the input file or converts an entire folder into a TAR
    archive.
2.  Tests multiple compression methods: raw, zlib-9, bz2-9, and several
    LZMA/XZ configurations.
3.  Automatically selects the method that produces the smallest output.
4.  Creates a container containing the `B01X` header, original file
    size, SHA-256 hash, original filename, and compressed data.
5.  When `--png` is enabled, the container is converted into RGB pixel
    data (1 pixel = 3 bytes) and divided into PNG shards. Each shard
    contains its own small header (`B01P`, index, count, and length).

PNG compression level 0 is used because the data has already been
compressed. Additional Deflate compression would provide little or no
benefit.

## Important Notes

-   **Do not modify the PNG files:** Resizing, cropping, taking
    screenshots, converting to JPEG, or using services that recompress
    images (such as WhatsApp Photo mode or social media platforms) can
    corrupt the embedded data. Always send PNGs as files or documents.
-   **Keep all parts together:** If even one `part_XXXXXX.png` file is
    missing from a multi-PNG set, restoration will fail. There is no
    parity or recovery backup.
-   **This is not encryption:** Anyone with the appropriate decoder can
    extract the original data. Encrypt your files separately before
    packing if they contain private information.
-   **Compression limitations:** Files that are already compressed, such
    as MP4, JPEG, ZIP, APK, and encrypted files, cannot be significantly
    reduced by any lossless compression tool. Savings are usually small
    (often 0--10%). Text, logs, JSON, source code, and CSV files can
    achieve much higher compression (sometimes 70--90%).
-   **RAM requirements:** The entire input file is loaded into memory
    during processing. Very large files (GB-sized) may require
    substantial RAM.
-   **Always verify first:** Before deleting your original files,
    perform `pack` → `unpack` → hash comparison to confirm that
    restoration works correctly.
-   **Keep the decoder available:** Store `b01file4.py` or
    `unpack_png.py` alongside your PNG files. The decoder is required to
    restore the original data.

## Test Results (Using This Tool)

  Data                          Original Size          Output Size   Space Saved
  --------------------------- --------------- -------------------- -------------
  MP4 video (9.9 MB)              9,892,375 B   9,873,579 B (.b01)         0.19%
  Log text (11 MB)               11,046,096 B     818,188 B (.b01)         92.6%
  `.mcpack` shader (1.3 MB)       1,330,234 B    1,217,060 B (PNG)          8.5%

## Technical Format (For Writing Your Own Decoder)

### PNG Shard Format

RGB, 3 bytes per pixel, row-major order, with zero padding at the end.

``` text
"B01P" | index u32 | count u32 | length u64 | data[length]
```

All integer values use big-endian byte order.

Concatenate the `data` sections from all shards in index order to
reconstruct the container.

### Container Format

``` text
"B01X" | ver=4 | method u8 | orig_size u64 | payload_size u64 | name_len u16
       | sha256(original) [32] | name | payload
```

### Compression Methods

  Method   Compression
  -------- --------------------
  `0`      Raw (uncompressed)
  `1`      zlib
  `2`      bz2
  `3`      LZMA (XZ)

Decompress the payload using the specified method, then compare the
SHA-256 hash against the original hash stored in the container.

If both hashes match, the original data has been restored without
modification.
