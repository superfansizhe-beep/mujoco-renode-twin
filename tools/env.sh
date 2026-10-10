#!/usr/bin/env bash
# Full local environment for this machine (macOS / arm64).
#
#   source tools/env.sh
#
# Brings up the three things the test suite expects but the machine does not
# provide by default:
#
#   1. newlib for the F407 firmware build -- Homebrew's arm-none-eabi-gcc
#      ships without it, so firmware/*/build.sh dies on #include <math.h>.
#      The sysroot lives in .toolchain/newlib (git-ignored, ~50 MB).
#   2. RENODE_PORTABLE / PYRENODE_PATH -- pyrenode3 wants a .NET portable
#      package. The Renode.app in /Applications is a desktop bundle, but its
#      Contents/MacOS directory *is* that package, so point at it.
#   3. nothing else: hostc, the viewer and the sim all work as installed.
#
# Run tools/fetch_newlib.sh once first if .toolchain/newlib is absent.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEWLIB_ROOT="${NEWLIB_ROOT:-$REPO_ROOT/.toolchain/newlib}"

if [ -f "$NEWLIB_ROOT/dev/usr/include/newlib/math.h" ]; then
  export C_INCLUDE_PATH="$NEWLIB_ROOT/dev/usr/include/newlib"
  export NEWLIB_ROOT
else
  echo "warning: no newlib at $NEWLIB_ROOT -- run tools/fetch_newlib.sh" >&2
fi

# Renode: prefer a real portable package, fall back to the installed app.
if [ -z "${RENODE_PORTABLE:-}" ]; then
  for cand in /Applications/Renode.app/Contents/MacOS "$HOME/renode_portable"; do
    if [ -d "$cand" ]; then RENODE_PORTABLE="$cand"; break; fi
  done
fi
if [ -n "${RENODE_PORTABLE:-}" ]; then
  export RENODE_PORTABLE
  export PYRENODE_PATH="${PYRENODE_PATH:-$RENODE_PORTABLE}"
fi

echo "env.sh: newlib=${NEWLIB_ROOT:+ready}${NEWLIB_ROOT:-missing} renode=${RENODE_PORTABLE:-unset}"