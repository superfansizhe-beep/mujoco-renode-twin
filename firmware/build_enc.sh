#!/bin/sh
# Build the encoder bring-up firmware: bash firmware/build_enc.sh
# (artifact enc_bringup.elf). Same compile discipline as the other
# builds; links startup + timer + the quadrature encoder driver.
set -e
cd "$(dirname "$0")"
CC="${ARM_GCC:-arm-none-eabi-gcc}"

# Same newlib discovery as twin/race build.sh: Homebrew's gcc has no math.h
# or libc, so `-lm` fails to resolve without the multilib -L.
NEWLIB_ROOT="${NEWLIB_ROOT:-${TMPDIR:-/tmp}/newlib}"
if [ ! -f "$NEWLIB_ROOT/dev/usr/include/newlib/math.h" ]; then
  _repo_root="$(cd .. && pwd)"
  if [ -f "$_repo_root/.toolchain/newlib/dev/usr/include/newlib/math.h" ]; then
    NEWLIB_ROOT="$_repo_root/.toolchain/newlib"
  fi
fi
if [ -f "$NEWLIB_ROOT/dev/usr/include/newlib/math.h" ]; then
  if [ -z "${C_INCLUDE_PATH:-}" ]; then
    C_INCLUDE_PATH="$NEWLIB_ROOT/dev/usr/include/newlib"
    export C_INCLUDE_PATH
  fi
  MULTILIB="$NEWLIB_ROOT/runtime/usr/lib/arm-none-eabi/newlib/thumb/v7e-m+fp/hard"
  if [ -d "$MULTILIB" ]; then
    printf '#!/bin/sh\nexec %s "$@" -L %s\n' "$CC" "$MULTILIB" > "$NEWLIB_ROOT/arm-gcc.new"
    if ! cmp -s "$NEWLIB_ROOT/arm-gcc.new" "$NEWLIB_ROOT/arm-gcc" 2>/dev/null; then
      mv "$NEWLIB_ROOT/arm-gcc.new" "$NEWLIB_ROOT/arm-gcc"
      chmod +x "$NEWLIB_ROOT/arm-gcc"
    else
      rm -f "$NEWLIB_ROOT/arm-gcc.new"
    fi
  fi
  [ -x "$NEWLIB_ROOT/arm-gcc" ] && CC="$NEWLIB_ROOT/arm-gcc"
fi
FLOAT="-mfloat-abi=hard -mfpu=fpv4-sp-d16"
[ "${SOFT:-0}" = "1" ] && FLOAT="-mfloat-abi=soft"

CFLAGS="-mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles -ffreestanding -fno-builtin -O2 -g -Wall -Wextra"
for src in startup timer_monotonic stm32f4_encoder enc_bringup; do
    "$CC" $CFLAGS -c $src.c -o $src.o
done

"$CC" -mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles \
      -T stm32f407.ld \
      -Wl,-Map=enc_bringup.map \
      startup.o timer_monotonic.o stm32f4_encoder.o enc_bringup.o \
      -o enc_bringup.elf -lm -lgcc

rm -f startup.o timer_monotonic.o stm32f4_encoder.o enc_bringup.o

echo "built: $(ls -la enc_bringup.elf | awk '{print $5, $9}')"
