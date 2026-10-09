#!/bin/sh
# Build the eight-channel GPIO + pure line-law bring-up.
set -e
cd "$(dirname "$0")"
CC="${ARM_GCC:-arm-none-eabi-gcc}"
FLOAT="-mfloat-abi=hard -mfpu=fpv4-sp-d16"
[ "${SOFT:-0}" = "1" ] && FLOAT="-mfloat-abi=soft"
CFLAGS="-mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles -ffreestanding -fno-builtin -O2 -g -Wall -Wextra"
for src in startup timer_monotonic stm32f4_line line_bringup; do
    "$CC" $CFLAGS -c $src.c -o $src.o
done
"$CC" -mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles \
      -T stm32f407.ld -Wl,-Map=line_bringup.map \
      startup.o timer_monotonic.o stm32f4_line.o line_bringup.o \
      -o line_bringup.elf -lm -lgcc
rm -f startup.o timer_monotonic.o stm32f4_line.o line_bringup.o
echo "built: line_bringup.elf"
