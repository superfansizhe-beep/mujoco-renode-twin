#!/bin/sh
# Build the IMU bring-up firmware: bash firmware/build_imu.sh
# (artifact imu_bringup.elf). Same compile discipline as the twin/race
# builds; links the shared startup + timer + the I2C/MPU6050 drivers.
# SOFT=1 switches to soft-float (no FPU is used, hard float is harmless).
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
for src in startup timer_monotonic stm32f4_i2c mpu6050 imu_bringup; do
    "$CC" $CFLAGS -c $src.c -o $src.o
done

"$CC" -mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles \
      -T stm32f407.ld \
      -Wl,-Map=imu_bringup.map \
      startup.o timer_monotonic.o stm32f4_i2c.o mpu6050.o imu_bringup.o \
      -o imu_bringup.elf -lm -lgcc

rm -f startup.o timer_monotonic.o stm32f4_i2c.o mpu6050.o imu_bringup.o

echo "built: $(ls -la imu_bringup.elf | awk '{print $5, $9}')"
