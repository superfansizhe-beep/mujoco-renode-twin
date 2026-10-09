#!/usr/bin/env bash
# Download Debian's newlib for arm-none-eabi (macOS has no dpkg-deb, and
# Homebrew's arm-none-eabi-gcc ships without it -- see tools/f407_env.sh).
#
#   bash tools/fetch_newlib.sh && source tools/f407_env.sh
#
# Idempotent: skips whatever is already unpacked.
set -euo pipefail

NEWLIB_ROOT="${NEWLIB_ROOT:-/tmp/newlib}"
VER="4.5.0.20241231-1"
BASE="https://mirrors.aliyun.com/debian/pool/main/n/newlib"
cd "$NEWLIB_ROOT"

need=0
for d in dev runtime; do
  [ -d "$d/usr" ] || need=1
done
[ "$need" = 1 ] || { echo "newlib already unpacked at $NEWLIB_ROOT"; exit 0; }

for pkg in "libnewlib-dev_${VER}_all.deb" "libnewlib-arm-none-eabi_${VER}_all.deb"; do
  [ -s "$pkg" ] || { echo "downloading $pkg"; curl -sSLO "$BASE/$pkg"; }
done

# Unpack .deb (ar + data.tar.xz) with stdlib only -- no dpkg-deb on macOS.
python3 - "$NEWLIB_ROOT" <<'PY'
import io, lzma, sys, tarfile, os
root = sys.argv[1]
def extract(deb, dest):
    data = open(deb, 'rb').read()
    assert data[:8] == b'!<arch>\n', f"{deb}: not an ar archive"
    off = 8
    while off < len(data):
        hdr = data[off:off+60]; off += 60
        if len(hdr) < 60: break
        name = hdr[0:16].decode().strip()
        size = int(hdr[48:58].decode().strip())
        body = data[off:off+size]; off += size + (size % 2)
        if not name.startswith('data.tar'):
            continue
        raw = lzma.decompress(body) if name.endswith('.xz') else body
        os.makedirs(dest, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            t.extractall(dest)
        print(f"  {name} -> {dest}")
        return
    raise SystemExit(f"{deb}: no data.tar member")

for ver in ("4.5.0.20241231-1",):
    extract(f"libnewlib-dev_{ver}_all.deb", os.path.join(root, "dev"))
    extract(f"libnewlib-arm-none-eabi_{ver}_all.deb", os.path.join(root, "runtime"))
PY

echo "ok. next:  source tools/f407_env.sh && bash firmware/twin/build.sh"