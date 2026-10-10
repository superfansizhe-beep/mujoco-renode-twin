#!/bin/sh
# Build the race firmware: bash firmware/race/build.sh   (artifact race_fw.elf)
# Same two-step compile as twin/build.sh; the relative-path .o
# keeps the username out of the map.
# Needs arm-none-eabi-gcc; when not on PATH, point ARM_GCC at the full path.
# SOFT=1 switches to soft-float.
# -I../twin: the balance gains come from the twin firmware's generated
# twin_fwconfig.h -- one single source for both ELFs' control core.
set -e
cd "$(dirname "$0")"
CC="${ARM_GCC:-arm-none-eabi-gcc}"

# Same newlib discovery as twin/build.sh: Homebrew's gcc has no math.h, and
# the test suite runs this script in a subprocess with no exported env.
NEWLIB_ROOT="${NEWLIB_ROOT:-${TMPDIR:-/tmp}/newlib}"
# Fall back to the repo-local toolchain (survives a cleaned TMPDIR, which is
# how CI and the test suite usually run).
if [ ! -f "$NEWLIB_ROOT/dev/usr/include/newlib/math.h" ]; then
  # We already cd'd into firmware/<name>/, so the repo root is two levels up.
  _repo_root="$(cd ../.. && pwd)"
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
  # (Re)write the wrapper so its -L always matches the NEWLIB_ROOT in use --
  # a stale one may still point at a cleaned /tmp.
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

# Two-step compile: in a one-step build, gcc generates the intermediate .o
# under %TEMP%, and its absolute path (containing the username) gets recorded
# in the map distributed with the artifact; writing main.o to a relative path
# first, then linking, avoids it (same comment, same reason as the radar repo).
CFLAGS="-mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles -ffreestanding -fno-builtin -I../twin -O2 -g -Wall -Wextra"
"$CC" $CFLAGS -c ../startup.c -o startup.o
"$CC" $CFLAGS -c ../timer_monotonic.c -o timer_monotonic.o
"$CC" $CFLAGS -c ../stm32f4_i2c.c -o stm32f4_i2c.o
"$CC" $CFLAGS -c ../mpu6050.c -o mpu6050.o
"$CC" $CFLAGS -c ../stm32f4_encoder.c -o stm32f4_encoder.o
"$CC" $CFLAGS -c ../stm32f4_adc.c -o stm32f4_adc.o
"$CC" $CFLAGS -c ../stm32f4_pwm.c -o stm32f4_pwm.o
"$CC" $CFLAGS -c ../stm32f4_line.c -o stm32f4_line.o
"$CC" $CFLAGS -c ../stm32f4_uart.c -o stm32f4_uart.o
"$CC" $CFLAGS -c ../uart_proto.c -o uart_proto.o
"$CC" $CFLAGS -c ../stm32f4_iwdg.c -o stm32f4_iwdg.o
"$CC" $CFLAGS -c ../core/balance.c -o balance.o
"$CC" $CFLAGS -c track.c -o track.o
"$CC" $CFLAGS -c race_law.c -o race_law.o
"$CC" $CFLAGS -c main.c -o main.o

"$CC" -mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles       -T ../stm32f407.ld       -Wl,-Map=race_fw.map       main.o race_law.o track.o balance.o stm32f4_i2c.o mpu6050.o stm32f4_encoder.o stm32f4_adc.o stm32f4_pwm.o stm32f4_line.o stm32f4_uart.o uart_proto.o stm32f4_iwdg.o startup.o timer_monotonic.o -o race_fw.elf -lm -lgcc

rm -f main.o race_law.o track.o balance.o stm32f4_i2c.o mpu6050.o stm32f4_encoder.o stm32f4_adc.o stm32f4_pwm.o stm32f4_line.o stm32f4_uart.o uart_proto.o stm32f4_iwdg.o startup.o timer_monotonic.o

echo "built: $(ls -la race_fw.elf | awk '{print $5, $9}')"
