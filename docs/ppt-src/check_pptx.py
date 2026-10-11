#!/usr/bin/env python3
"""Verify a built deck before shipping it.

A picture whose bytes do not match its extension is the failure mode that
bit this deck once: `task2.png` held JPEG data, pptxgenjs wrote it as
image/png, the entry CRC went bad, and PowerPoint rendered an empty frame
with no error message. Both halves are cheap to check, so check both.

    python3 docs/ppt-src/check_pptx.py [path/to.pptx]

Exits non-zero on the first problem found.
"""
import hashlib
import os
import struct
import sys
import zipfile

try:
    from PIL import Image
except ImportError:  # Pillow is not required for the CRC half of the check
    Image = None

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "mujoco-renode-twin-defense.pptx")

# what the extension promises, and what PIL should agree with
TRUTH = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}


def png_chunks_ok(blob):
    """Walk every PNG chunk and verify its CRC. Returns (ok, detail)."""
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        return False, "missing PNG signature"
    off, seen = 8, []
    while off + 8 <= len(blob):
        length = struct.unpack(">I", blob[off:off + 4])[0]
        end = off + 12 + length
        if end > len(blob):
            return False, f"truncated chunk #{len(seen)}"
        kind, data = blob[off + 4:off + 8], blob[off + 8:off + 8 + length]
        crc = struct.unpack(">I", blob[off + 8 + length:off + 12 + length])[0]
        if _crc32(kind + data) != crc:
            return False, f"chunk {kind.decode('latin1', 'replace')} CRC mismatch"
        seen.append(kind.decode("latin1", "replace"))
        off = end
        if kind == b"IEND":
            break
    if off != len(blob):
        return False, f"{len(blob) - off} trailing bytes after IEND"
    return True, " + ".join(seen)


def _crc32(data):
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if not os.path.exists(path):
        print(f"FAIL: no such deck: {path}")
        return 1

    problems = []
    with zipfile.ZipFile(path) as z:
        broken = z.testzip()
        if broken:
            problems.append(f"corrupt zip entry (CRC): {broken}")

        media = [n for n in z.namelist()
                 if n.startswith("ppt/media/") and not n.endswith("/")]
        if not media:
            problems.append("no media in the deck - images were never embedded")

        for name in sorted(media):
            try:
                blob = z.read(name)
            except Exception as exc:  # a bad CRC surfaces here
                problems.append(f"{name}: unreadable ({type(exc).__name__}: {exc})")
                continue

            ext = os.path.splitext(name)[1].lower()
            want = TRUTH.get(ext)
            if Image is not None and want:
                try:
                    got = Image.open(__import__("io").BytesIO(blob)).format
                except Exception as exc:
                    problems.append(f"{name}: not decodable ({type(exc).__name__})")
                    continue
                if got != want:
                    problems.append(f"{name}: bytes are {got}, extension says {want}")
            if ext == ".png":
                ok, detail = png_chunks_ok(blob)
                if not ok:
                    problems.append(f"{name}: {detail}")

    slides = 0
    with zipfile.ZipFile(path) as z:
        slides = sum(1 for n in z.namelist()
                     if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                     and "/_rels/" not in n)

    if problems:
        print(f"FAIL {os.path.basename(path)} ({os.path.getsize(path)} bytes)")
        for p in problems:
            print(f"  - {p}")
        return 1

    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    print(f"OK   {os.path.basename(path)}: {slides} slides, "
          f"{len(media)} media, zip intact, sha={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())