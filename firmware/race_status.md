# Race bring-up status -- SIM vs BOARD

One C mission law (firmware/race/race_law.c), compiled for both the host C
backend and the ARM firmware. firmware/race/main.c retains the v3 peripheral
and serial shell, with one production controller surface (race/renode_backend.py::
RacePeriphBackend). The peripheral set: MPU6050 over the real I2C
driver, TIM3/TIM4 encoder interface, the 8xIO line bar on PF0-PF7
(stm32f4_line.c), battery on ADC1, TIM1/TB6612 drive, buzzer/LED on
PF8/PF9, and the USART2 Bluetooth link (stm32f4_uart.c + the shared
uart_proto.c core, twin parity). The task word is
mission configuration the harness writes into the RAC2 window
pre-boot; telemetry mirrors keep the grader's contract.

## SIM -- peripheral contract (tests/test_race_firmware.py, Renode 1.17.0)

| gate | test |
| --- | --- |
| task 1 through the peripheral path: stub lockstep, events equal, grade PASS, heartbeat 100/100 | `test_firmware_runs_task1_and_tracks_stub` |
| tasks 2-3 through the peripheral path: both grade PASS on the kinked routes | `test_firmware_runs_tasks_23_through_peripherals` |
| task 4 through the 2026-09-30 profile: four laps, 16/16 nodes in order, grade PASS at 119.199 s, stop error 0.056 m; both counters wrap twice (2/2 crossings), heartbeat 23906/23906 | `test_firmware_runs_task4_through_peripherals_and_wraps_encoders` (150 s budget); [RCC evidence](evidence/rcc-gating-20260930.json) |
| the serial link during a mission (v3): task 2 with the TX tap -- UP, 10 Hz telemetry with honest mission fields, ping/stat answered mid-run, node lines 1-2-3, the done line, starved/resume, grade still PASS, heartbeat exact | `test_production_elf_talks_on_the_serial_link_during_a_mission` |
| GPIOF config (PF0-7 inputs + pulls, AHB1ENR.GPIOF readback) at runtime | `test_firmware_line_bar_config_is_written_at_runtime` |
| bar feed reaches the law: pin levels drive e_lat inside the cycle (exercised end-to-end by the tape-following lockstep) | (via the e2e) |

Probes (output/race-integration/): `gpioPortF OnGPIO` drives the IDR
(level-based, no RunFor needed) -- the honest line-bar feed.

The Renode 1.17 encoder overflow wall is resolved by `enc_model.cs`, the
same approach as the ADC model: TIM3/TIM4 retain the driver's x4 register
contract and the harness's `OnGPIO` protocol, with CNT wrapping at 16 bits
on each edge. The C control law, constants, and modular encoder driver
are unchanged. Wrap/underflow and model limits are covered in
[enc_status.md](enc_status.md). The long probe passed +70000/-70000
counts with 10000/10000 firmware cycles; the field E2E above verifies the
four-lap score as well. Evidence: `output/encoder-wrap/coupling-probe.log`
and `output/encoder-wrap/full-gates.log`.

The 2026-09-29 full-workspace regression cited in older notes (141 tests,
`output/encoder-wrap/full-gates.xml`) belongs to the pre-line-tuning profile.
The pre-RCC-gating profile's green records are `output/line-fidelity/native-software-gates.json`
(104), `native-twin-functions.json` (24), `native-line-matrix.json` (14/14),
`native-task4.json` and `native-race-peripheral-gates.json` -- all zero failures/
errors/skips with unchanged source/ELF hashes.

The 2026-09-30 RCC-enable model has separate verification in
[rcc_status.md](rcc_status.md). The older records are retained as evidence
for their pinned model snapshot, not automatically reused for this change.
The new [RCC evidence](evidence/rcc-gating-20260930.json) includes a fresh
Task 1/stub comparison, CLI/native-input checks and Task 4 PASS at 119.199 s,
16/16 nodes, 0.056 m stop error, two wraps per wheel and heartbeat 23906/23906.

## Speed tuning (2026-10-01, SIM)

The owner confirmed the modeled JGB37-520 1:30 motors, 80 mm wheels and
3S/11.1 V nominal battery. Turbo straight/bend/node targets are now
0.28/0.26/0.20 m/s. The yaw filter is 40 Hz; a separate 10 Hz encoder-velocity
estimate feeds the stopped check. Raw deltas still drive odometry and balance,
and the speed/yaw thresholds and 450 ms stop hold are unchanged.

The production ELF's nominal Task 4 grade is PASS: 16/16 nodes in order,
0.019 m stop error, two wraps per wheel and heartbeat 19233/19233. Pure world
driving time is 95.865 s (firmware-reported mission clock 95.847 s), compared
with 119.230 s of world driving time in the fresh frozen baseline. These
world measurements exclude the 0.30 s arming interval and host computation
slowdown; MCU/sensor/actuator latency stays in the control loop. Median body
speed is 0.28775 m/s on straights and 0.2682 m/s on bends.

`python -m race.speed_probe --backend renode --task 4 --output output/race-speed.json`
repeats the measurement. Add `--stress` for 10.5 V, floor friction 1.0, a shove
at 10 s and an extra 5 ms actuator hold. Physical speed and timing validation
remain BOARD gates below; these simulation results do not certify them.

The combined stress run passes in 101.320 s of world driving time: all
16 nodes, 0.031 m stop error, two wraps per wheel and heartbeat 20324/20324.
Stopped-body peak speed is 0.0279 m/s during the 450 ms hold. The new and
retained validation records, source hashes and rejected profiles are in
[speed-tuning-20261001.json](evidence/speed-tuning-20261001.json).

The backend observation layer records bounded sequence-numbered events and
separate host coupling timing; the viewer has no diagnostic controls.
Normal viewer frames skip C symbol reads and diagnostic history. Optional
`--monitor-stream` exposes `state.debug` to the terminal client and snapshots
always include it. Optional
`--serial-debug` captures the existing USART2 traffic and queues ping/stat
through normal coupled steps. `--gdb-port` requires `--serve --paused`;
GDB memory inspection and cold-reset reattachment pass without advancing
the plant or law. No C ELF change was needed for this layer. See
[backend monitoring](../race/README.md#backend-monitoring-and-event-stream)
for the protocol, terminal commands and GDB launch instructions.

Backend performance is measured separately from world driving speed by
`python -m race.perf_probe`. The current bounded native C/Renode medians
are 11.06/0.160 world seconds per wall second; the production ELF is
unchanged. `ops.py start race --backend hostc` enables normal-world pacing
for interactive commands. The profiler records CPU, memory, step latency,
hotspots and heartbeat continuity without adding monitoring UI. See
[backend profiling](../race/README.md#backend-performance-profiling) and
[runtime-performance-20261001.json](evidence/runtime-performance-20261001.json)
for measurement scope, validation and rejected experiments.

## The serial link (v3 shell, twin parity)

Same driver and protocol core as the twin shell (firmware/uart_status.md
owns the pin contract, the Renode findings and the generic board
labels). The outer loop polls IMU data-ready in 2 ms slices so
`uart_pump()` runs between samples (commands answer within ~2-7 ms); the
starvation rule lives in the shell (same 150 ms window, zero duty +
buzzer/LED off, heartbeat freeze, resume on the next fresh sample).
Line protocol, `\n`-terminated:

| line | meaning |
| --- | --- |
| `UP` | boot complete (after all inits, right before the loop) |
| `T <seq> <dl> <dr> <batt_mv> <t_ms> <seg> <phase>` | 10 Hz telemetry (every 20th 200 Hz cycle) and the `stat` answer; seq = the RAC2 heartbeat, dl/dr = per-wheel permille, t_ms = the mission clock (0 while arming), seg = segment index (0-based, reaches route length while braking), phase = 0 arm / 1 run / 2 brake / 3 done |
| `node <seg>` | a leg was completed; the car enters leg `seg` (0-based, route order) |
| `done <t_ms>` | arrival: the brake settled, mission clock in ms |
| `starved` / `resume` | supervision transitions (no fresh IMU sample for 150 ms / first fresh sample after) |
| `pong` | the `ping` answer; unknown lines are ignored silently |

## BOARD -- pending hardware (procedure for the arrival day)

| gate | procedure |
| --- | --- |
| line-board identity | confirm the purchased 8-way board matches the YB-MX04-2.0 reference: 8xIO vs I2C vs USART interface actually wired; if USART was chosen, the UART milestone's driver replaces stm32f4_line.c and UART becomes a control input |
| bar polarity | `LINE_SENSORS_ACTIVE_LOW` in stm32f4_line.h assumes the module pulls LOW on-tape; check one sensor over white/black with a meter and flip if wrong |
| channel order + pitch | bar channel i must map to PF i with i growing +x (the law's bar frame); caliper the sensor pitch against RACE_LINE_PITCH, black-tape sweep to verify bit order |
| mounting height | detect height band 5-60 mm: set the bar drop below the lower disc so sensors ride 10-30 mm over the KT板 |
| 5 V levels | module output high is 5 V: PF0-7 must be the FT (five-volt-tolerant) pins or get series resistors -- check the datasheet table before wiring |
| buzzer/LED electrical | PF8 drives the active buzzer (transistor if it wants >20 mA), PF9 the LED + resistor; scope the beep edges against RACE_BUZZER_MS |
| motors | pwm_status.md's TB6612 truth table + direction-pin swap applies per wheel; race duty + is chassis +Y, opposite the route's travel-forward direction (chassis -Y). Check both wheel signs on the board before running a mission |
| missions 1-4 on the physical field | all four sim gates pass through the peripheral path, including task 4's four figure-8 laps; repeat on the taped sheet with the grader's stopwatch, node-beep placement, and stop measurements |
| watchdog | IWDG wired in both production mains (firmware/stm32f4_iwdg.c: ~300 ms nominal at LSI/32, kicked every loop slice). The custom `iwdg_model.cs` now performs a real machine reset, and the gates prove no spurious reset on a healthy loop plus reset-on-starvation (`test_heartbeat_crosses_a_full_watchdog_window`). On the board only: meter the real LSI oscillator frequency and confirm the register-update latency against the timed-out reset |
| serial link | the wire/module labels live in [uart_status.md](uart_status.md) (pacing >= ~2 ms/byte for polled RX, module AT-baud, level shifts); race-specific: the telemetry line is ~40 bytes = ~3.5 ms of TXE-blocking wire time at 115200 once per 100 ms -- far under the 150 ms starvation window; a hands-on mission session needs the task word + bar, so drive it through the grader harness or extend twin/uart_session.py before track day |
