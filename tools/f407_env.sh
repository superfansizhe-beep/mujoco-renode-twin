#!/usr/bin/env bash
# F407 firmware toolchain env for this machine (macOS / arm64).
#
# Homebrew's arm-none-eabi-gcc ships WITHOUT newlib (no math.h, no stdint.h),
# so firmware/*/build.sh fails on `#include <math.h>`. Debian's newlib
# packages supply both headers and the ARM multilib libs.
#
#   source tools/f407_env.sh
#   bash firmware/twin/build.sh && bash firmware/race/build.sh
#
# Idempotent and machine-local: the .deb payloads live under NEWLIB_ROOT.
set -u

NEWLIB_ROOT="${NEWLIB_ROOT:-/tmp/newlib}"

if [ ! -f "$NEWLIB_ROOT/dev/usr/include/newlib/math.h" ]; then
  echo "newlib missing at $NEWLIB_ROOT -- run tools/fetch_newlib.sh first" >&2
  return 1 2>/dev/null || exit 1
fi

# build.sh honours $ARM_GCC; wrap the bare brew gcc with the multilib -L.
if [ ! -x "$NEWLIB_ROOT/arm-gcc" ]; then
  cat > "$NEWLIB_ROOT/arm-gcc" <<EOF
#!/bin/bash
exec arm-none-eabi-gcc "\$@" \\
  -L $NEWLIB_ROOT/runtime/usr/lib/arm-none-eabi/newlib/thumb/v7e-m+fp/hard
EOF
  chmod +x "$NEWLIB_ROOT/arm-gcc"
fi

export C_INCLUDE_PATH="$NEWLIB_ROOT/dev/usr/include/newlib"
export ARM_GCC="$NEWLIB_ROOT/arm-gcc"

# Renode: the .app in /Applications is a desktop bundle, not the portable
# .NET package pyrenode3 needs, so firmware-in-the-loop stays skipped here.
# Point RENODE_PORTABLE at a portable download to enable it.
export RENODE_PORTABLE="${RENODE_PORTABLE:-/Applications/Renode.app}"
export PYRENODE_PATH="${PYRENODE_PATH:-$RENODE_PORTABLE}"