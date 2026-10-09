#!/bin/sh
# Build the battery bring-up firmware: bash firmware/build_battery.sh
# (artifact battery_bringup.elf). Same compile discipline as the other
# builds; links startup + timer + the ADC driver.
set -e
cd "$(dirname "$0")"
CC="${ARM_GCC:-arm-none-eabi-gcc}"
FLOAT="-mfloat-abi=hard -mfpu=fpv4-sp-d16"
[ "${SOFT:-0}" = "1" ] && FLOAT="-mfloat-abi=soft"

CFLAGS="-mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles -ffreestanding -fno-builtin -O2 -g -Wall -Wextra"
for src in startup timer_monotonic stm32f4_adc battery_bringup; do
    "$CC" $CFLAGS -c $src.c -o $src.o
done

"$CC" -mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles \
      -T stm32f407.ld \
      -Wl,-Map=battery_bringup.map \
      startup.o timer_monotonic.o stm32f4_adc.o battery_bringup.o \
      -o battery_bringup.elf -lm -lgcc

rm -f startup.o timer_monotonic.o stm32f4_adc.o battery_bringup.o

echo "built: $(ls -la battery_bringup.elf | awk '{print $5, $9}')"
