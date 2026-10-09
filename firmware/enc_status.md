# Encoder bring-up status -- SIM vs BOARD

One driver (firmware/stm32f4_encoder.c), one bring-up ELF
(firmware/enc_bringup.c), two verification worlds. Pin contract:
TIM3 CH1/CH2 = PC6/PC7 (left), TIM4 CH1/CH2 = PD12/PD13 (right), both
AF2 with pull-ups; PB6/PB7 stay with I2C1, motor PWM keeps off these
pins (TIM8's PWM lands on PIx/TIM1 when the motor-driver module
settles).

## SIM -- verified (tests/test_firmware_encoder.py, Renode 1.17.0)

TIM3/TIM4 use the runtime-compiled `enc_model.cs` encoder slice. The
stock `STM32_Timer` throws on edge-driven 16-bit wrap/underflow; changing
its monitor `Limit` does not fix that path. The replacement counts the
same A/B transitions and bounds CNT to 16 bits on every edge. The real
C driver and its modular-delta integration are unchanged.

| gate | test |
| --- | --- |
| encoder-mode registers (SMS=011, CC1S=01/CC2S=01, CCER, CEN) + GPIO AF/pull + RCC enables (GPIOC/D, TIM3/4) visible at runtime | `test_encoder_mode_contract_is_written_at_runtime` |
| forward quadrature integrates +40 counts, raw CNT matches | `test_forward_counts_integrate_to_position` |
| reverse after a forward primer integrates 30-10 | `test_reverse_counts_negative_after_a_forward_primer` |
| a bench counter preset integrates through the same modular delta | `test_bench_counter_preset_integrates_as_a_modular_jump` |
| forward wrap 0xFFFE -> 0x0004 integrates all six edges | `test_forward_wrap_integrates_without_losing_counts` |
| reverse from zero wraps and integrates -40 counts | `test_reverse_from_zero_integrates_negative_position` |
| reverse underflow 0x0002 -> 0xFFFC integrates -6; DIR reports down | `test_reverse_underflow_integrates_without_losing_counts` |
| repeated pin levels do not create edges | `test_repeated_pin_levels_do_not_duplicate_edges` |
| CEN=0 freezes counting while preserving the current A/B phase | `test_disabled_counter_tracks_pins_without_counting` |
| unsupported SMS/input mapping/polarity/prescaler/ARR configurations do not count | `test_unsupported_encoder_configurations_do_not_count` |
| peripheral reset clears both pins, CNT, and configuration | `test_reset_clears_pin_state_and_configuration` |

Long coupling probe: `.venv/Scripts/python.exe -u -m tests.encoder_wrap_probe`
drives the production race backend with +70000
left / -70000 right counts, seven counts per 5 ms coupling. Every batch
checks CNT modulo 65536, and every coupling checks the firmware heartbeat.
It passed with 10000/10000 firmware cycles, one wrap in each direction,
and no fault. Evidence: `output/encoder-wrap/coupling-probe.log`.

## BOARD -- pending hardware (procedure for the on-arrival day)

| gate | procedure |
| --- | --- |
| silicon wrap and direction through the physical pins | with the wheel at CNT~0xFFFE, rotate forward through wrap and watch pos continue upward through the debugger at 0x2001EE08; repeat backward through zero and compare with the simulated gate |
| clock gating effect | [rcc_status.md](rcc_status.md) covers missing GPIOC/D configuration enables and TIM3/4 clocks in SIM; on the board verify a from-reset boot integrates quadrature and counts stop with the timer clock off |
| real AF routing | edges must reach the timers through PC6/PC7 + PD12/PD13 in AF2. The GPIO receiver guards reject a wrong MODER/AF2 slice in SIM; complete alternate-function wiring beyond these pins remains outside the modeled slice |
| electrical | quadrature A/B from the motor encoders, 3.3 V, pull-ups on; swap A/B on a motor that counts backward |

Sim limits accepted: edge injectors drive the GPIO port receivers
(`gpioPortC`/`gpioPortD` OnGPIO -- the same receivers the monitor calls), not
direct CNT writes and not `timer OnGPIO`, so the path exercises the GPIO
MODER/AF2 guards and the 20 us quadrature edge timing. The timer model supports
the driver's unfiltered, noninverted x4 configuration only (PSC=0, ARR=0xFFFF,
CCMR1=0x101, SMS=011). Interrupts, other timer modes, input filters, polarity
changes, and prescaling are outside this slice.
