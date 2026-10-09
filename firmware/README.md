# Firmware board-driver policy

Decision, 2026-09-29: **HAL and LL are deferred during the Renode twin phase.**
Keep the handwritten register drivers. The inclusion gate below opens only
after the existing bring-up fails on physical hardware for a specific
peripheral.

## Rationale

1. **The integration boundary is the board layer.** The shared balance law in
   [core/](core/balance.h) and the race task laws must remain platform-agnostic
   C. The twin/race shells use mailbox RAM and TIM2; separate bring-up firmware
   exercises I2C/MPU6050, ADC1, TIM1 PWM and TIM3/TIM4 encoders. Their register
   paths have named Renode gates in the peripheral status files below. A
   library substitution would require revalidating those paths. Simulation
   evidence covers only modeled behavior: for example, [pwm_status.md](pwm_status.md)
   records simulated BDTR read-back and motor-drive gating while electrical
   waveforms and within-period timing remain board checks.
2. **Boot and clock compatibility would become additional work.**
   [startup.c](startup.c) keeps reset handling local; the firmware retains the
   16 MHz HSI reset clock, and [stm32f407zg.repl](stm32f407zg.repl) pins timer
   frequencies to match. [rcc_status.md](rcc_status.md) records negative
   clock-enable gates for the peripherals the firmware uses; frequency
   derivation and real oscillator behavior remain separate checks.
   Importing Cube/CMSIS startup or clock setup would require checking ready
   flags, flash latency, clock frequencies and the timeout timebase. These are
   separate choices from adopting a peripheral driver: `SystemInit` belongs
   to [CMSIS](https://github.com/STMicroelectronics/cmsis-device-f4/blob/master/Source/Templates/system_stm32f4xx.c).
   [HAL RCC waits](https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/master/Src/stm32f4xx_hal_rcc.c)
   use `HAL_GetTick()` timeouts; an advancing tick can return `HAL_TIMEOUT`,
   while a stalled tick can leave a readiness wait stuck. A HAL boot hang has
   not been demonstrated here.
3. **A/B discipline and configuration should stay simple.** HAL would expand
   the reviewed dependency and configuration surface, including `hal_conf`,
   MSP hooks and any timebase support. CubeMX generation must not become a
   second source of control constants: [twin.fwconfig](../twin/fwconfig.py) and
   [race.fwconfig](../race/fwconfig.py) remain authoritative for their generated
   headers. Keep the mailbox reference and firmware comparisons intact.

## Stable board interfaces

The existing C headers are the substitution seams; preserve signatures,
units, status meanings and deadline behavior when changing an implementation.

| Interface | Contract to preserve | Evidence and board procedure |
| --- | --- | --- |
| [stm32f4_i2c.h](stm32f4_i2c.h) | Register transfers, microsecond deadlines, OK/timeout/NACK status | [imu_status.md](imu_status.md) |
| [mpu6050.h](mpu6050.h) | Raw sample layout, identity/config checks, bounded data-ready acquisition | [imu_status.md](imu_status.md) |
| [stm32f4_adc.h](stm32f4_adc.h) | Conversion status separate from value; zero is valid; raw and millivolt units | [battery_status.md](battery_status.md) |
| [stm32f4_pwm.h](stm32f4_pwm.h) | Signed permille, forward sign, rail clamp and zero-duty coast | [pwm_status.md](pwm_status.md) |
| [stm32f4_encoder.h](stm32f4_encoder.h) | Counter reads and signed modular deltas | [enc_status.md](enc_status.md) |
| [stm32f4_uart.h](stm32f4_uart.h) | Per-byte deadline TX, nonblocking RX, TC flush; status separate from data | [uart_status.md](uart_status.md) |
| [timer_monotonic.h](timer_monotonic.h) | Raw ticks, elapsed microseconds, wrap-safe subtraction | [test_firmware_board.py](../tests/test_firmware_board.py), [battery_status.md](battery_status.md) |

Keep HAL/LL types, handles, headers and calls inside board implementations.
The wrapper must translate library results into the existing API contract;
`core/` and race task laws must not acquire device-library dependencies.
Any future clock change must update the `.repl` frequencies,
`TIMER_TICKS_PER_US` and affected peripheral timing together.

## Inclusion gate after hardware arrives

1. Run the existing register-based bring-up on the real board first, using
   the BOARD procedures in the relevant status file.
2. Record a reproducible hard failure for the affected peripheral, including
   board wiring, firmware revision, observed status/timing and debugger or
   scope evidence. An MPU6050 I2C hang is an example trigger, not an observed
   hardware failure today. Hardware availability alone does not open the gate.
3. Select a replacement for that peripheral only. Prefer LL when register-level
   substitution is sufficient; use HAL when its driver support addresses the
   demonstrated failure. LL still needs contract and hardware verification.
4. Vendor the selected STM32CubeF4 driver component under `firmware/vendor/`,
   pin its release/commit, retain its license and notices, and list the sources
   and necessary support files included in the build. The official
   [HAL/LL driver component license](https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/master/LICENSE.md)
   is BSD-3-Clause. Implement the replacement behind the existing board API,
   with the required clock enables, pin setup and bounded timeout timebase.
   Keep startup, clock ownership, `core/`, race task laws, mailbox contracts
   and the `fwconfig` generators under the existing project boundaries.
5. Prove the failure is resolved on hardware, including timeout/recovery and
   the relevant BOARD checks. Rerun the board and affected peripheral Renode
   suites, generated-header/mailbox checks and twin/race A/B comparisons.
   Record model limitations and skips explicitly; they do not count as passes.
   Update the peripheral status file with the before/after evidence before
   marking the replacement validated.

Until that gate is met, do not add HAL/LL sources, CubeMX projects, or vendor
configuration templates to the repository.
