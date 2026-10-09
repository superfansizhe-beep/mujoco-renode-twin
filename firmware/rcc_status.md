# RCC enable gating -- SIM vs BOARD

The production firmware keeps the 16 MHz HSI reset profile. `rcc_model.cs`
wraps Renode 1.17's stock RCC register model and gates only the peripherals
the current drivers use: GPIOA-F, TIM1-4, I2C1, USART2 and ADC1.

Reference: [RM0090 Rev 22](https://www.st.com/resource/en/reference_manual/dm00031020.pdf),
STM32F405/407 sections 7.3.10 (AHB1ENR, page 243), 7.3.13 (APB1ENR,
page 246) and 7.3.14 (APB2ENR, page 249). These define each peripheral's
clock enable independently of its own control registers.

## Probe and implementation

With the CPU executing a self-branch, the stock platform counted 1000 TIM2
ticks in 1 ms with PSC=15 and **APB1ENR=0**. RCC readback alone therefore
missed a dead-clock firmware defect. `output/rcc-gating/probe.log` records
the local Renode API inventory and this reproduction.

The installed 1.17 API provides `SystemBus.SetPeripheralEnabled` and
`ClockSource.ExchangeClockEntryWith`, but its `ClockEntry.With` has no
`clocked` argument. The model disables bus access and saves/clears each
owned clock entry's Enabled state; restoring the enable preserves count,
phase and fractional time. Machine reset discards the saved state.
The encoder model and the UART wire model (uart_model.cs) also guard
asynchronous input, which bypasses bus access. GPIO pin configuration is retained after
disabling its clock; AF signals are not artificially disconnected.

`RenodeChannel.preset_counter` sets harness initial conditions directly
before CPU execution, without setting RCC bits. It rejects runtime use.
This preserves the encoder origin and TIM2 wrap tests while keeping
firmware responsible for its own clock enables.

## SIM gates

`.venv/Scripts/python.exe -m unittest tests.test_firmware_rcc -v`

| Negative case and recovery | Gate |
| --- | --- |
| Configuration written with each of the 13 clock enables absent is discarded; enabling permits configuration | `test_disabled_register_writes_do_not_configure_peripherals` |
| CEN before TIM2 clock enable has no effect; removal stops count, restoration resumes | `test_tim2_clock_stops_preserves_and_resumes_counter` |
| Encoder pin edges with TIM3 clock removed do not count; restoration recovers | `test_encoder_clock_blocks_edges_and_recovers` |
| ADC1 cannot start a conversion without its clock, then recovers | `test_adc_cannot_convert_with_its_clock_disabled` |
| Machine reset while a timer is suspended cannot restore its old CEN/count | `test_reset_does_not_resume_previous_timer_state` |
| USART2 drops wire input with clock removed; restored input reaches RXNE/DR | `test_usart_clock_discards_wire_input_and_recovers` |
| TIM1 PWM timer clocks pause and resume without resetting count | `test_tim1_pwm_clock_entries_pause_and_resume` |

The initial five-test reproduction produced 14 failing assertions/subtests.
The seven final RCC gates passed with the board, IMU, encoder, PWM, battery
and UART suites: **69 tests, zero failures/errors/skips**. The balance twin
function runner passed **25/25**, including production ELF/stub comparison
and serial supervision. Race/CLI verification passed **6/6**, including
Task 1/stub lockstep and Task 4: four laps in 119.199 s, 16/16 ordered
nodes, 0.056 m stop error, two wraps per wheel, heartbeat 23906/23906.
Both generated-header `--check` commands passed.

The durable [evidence record](evidence/rcc-gating-20260930.json) contains
source, ELF and log hashes, the grade, environment versions and declared
scope. Raw local logs live in `output/rcc-gating/`. The RCC source's manual
revision comment was corrected to Rev 22 after the peripheral suite;
executable logic did not change. The record explicitly notes this delta.

## Scope and BOARD checks

This closes the clock-enable slice, not clock-frequency derivation. PLL,
APB prescalers, oscillator variation, enable propagation delay, low-power
clocks, RCC reset-bit effects and unused peripherals remain unmodeled.
The disabled bus returns zero on reads and discards writes; this is an
explicit simulator convention, not a measured silicon readback guarantee.
It does not add GPIO/AF validation to I2C or UART's logical wire paths.
GPIOA/B configuration omissions are caught by the register gate; actual
wire routing must still be verified on the board. Existing encoder AF
guards continue to apply.

TIM1 clock removal freezes its modeled waveform state; the plant's
existing drive decoder conservatively suppresses torque when a clock is
off. Scope the physical frozen pin level rather than assuming coast.
UART wire pacing/ORE and MPU6050 range scaling landed the same day:
uart_status.md and imu_status.md carry their gates.

On hardware, verify cold boot, enable delay, TIM2 tick rate, encoder
count stop/resume, ADC conversion recovery, serial input and PWM output
with the clock removed. No BOARD gate is marked verified by this change.
