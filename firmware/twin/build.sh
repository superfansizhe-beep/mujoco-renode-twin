#!/bin/sh
# Build the balance firmware: bash firmware/twin/build.sh   (artifact balance_fw.elf)
# Needs arm-none-eabi-gcc; if it is not on PATH, give the full path via ARM_GCC.
# Defaults to hard float (M4F, CPACR enabled inside the firmware); if Renode
# has trouble with FPU instructions, switch to soft float with
# SOFT=1 bash firmware/twin/build.sh — the control core is ~50 flop/cycle,
# performance is irrelevant at 200Hz.
set -e
cd "$(dirname "$0")"
CC="${ARM_GCC:-arm-none-eabi-gcc}"
FLOAT="-mfloat-abi=hard -mfpu=fpv4-sp-d16"
[ "${SOFT:-0}" = "1" ] && FLOAT="-mfloat-abi=soft"

# Two-step compile: in a one-step build, gcc generates the intermediate .o
# under %TEMP%, and its absolute path (containing the username) gets recorded
# in the map distributed with the artifact; writing main.o to a relative path
# first, then linking, avoids it (same comment, same reason as the radar repo).
CFLAGS="-mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles -ffreestanding -fno-builtin -O2 -g -Wall -Wextra"
"$CC" $CFLAGS -c ../startup.c -o startup.o
"$CC" $CFLAGS -c ../timer_monotonic.c -o timer_monotonic.o
"$CC" $CFLAGS -c ../stm32f4_i2c.c -o stm32f4_i2c.o
"$CC" $CFLAGS -c ../mpu6050.c -o mpu6050.o
"$CC" $CFLAGS -c ../stm32f4_encoder.c -o stm32f4_encoder.o
"$CC" $CFLAGS -c ../stm32f4_adc.c -o stm32f4_adc.o
"$CC" $CFLAGS -c ../stm32f4_pwm.c -o stm32f4_pwm.o
"$CC" $CFLAGS -c ../stm32f4_uart.c -o stm32f4_uart.o
"$CC" $CFLAGS -c ../uart_proto.c -o uart_proto.o
"$CC" $CFLAGS -c ../stm32f4_iwdg.c -o stm32f4_iwdg.o
"$CC" $CFLAGS -I. -c ../core/balance.c -o balance.o
"$CC" $CFLAGS -c main.c -o main.o

"$CC" -mcpu=cortex-m4 -mthumb $FLOAT -nostdlib -nostartfiles       -T ../stm32f407.ld       -Wl,-Map=balance_fw.map       main.o balance.o stm32f4_i2c.o mpu6050.o stm32f4_encoder.o stm32f4_adc.o stm32f4_pwm.o stm32f4_uart.o uart_proto.o stm32f4_iwdg.o startup.o timer_monotonic.o -o balance_fw.elf -lm -lgcc

rm -f main.o balance.o stm32f4_i2c.o mpu6050.o stm32f4_encoder.o stm32f4_adc.o stm32f4_pwm.o stm32f4_uart.o uart_proto.o stm32f4_iwdg.o startup.o timer_monotonic.o

echo "built: $(ls -la balance_fw.elf | awk '{print $5, $9}')"
