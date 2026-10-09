# Eight-channel line array: implementation and evidence

The race uses one optical model and one digital-mask contract for the Python
controller and the production C firmware. A set bit means **black detected**.
PF0–PF7 are active low; the physical GPIO level is the complement of that mask.
Channel indicators are **on over white and off over black**. Optical illumination
stays on; an indicator changing state does not disable the sensing light.

`python -m race --backend renode` and `race.ab_probe` select the production
peripheral backend: I2C IMU, GPIO line array, edge-fed encoders and PWM output.
The historical mailbox backend is not a valid input path for the current ELF.

`bot/line_sensor.py` projects each channel's downward optical axis onto the floor,
samples a finite footprint and applies hysteresis. `race/track.py` owns the black
tape geometry. The viewer draws the same annular sectors, without extending their
ends or showing untaped route guides as black tape. It displays eight indicators,
floor footprints, GPIO levels, raw detection and the correction source. Sensor
view follows the array, and Pause freezes physics and firmware together.

## Centering and recovery

Channels 0–7 increase along CAD +X, which is travel-left for this bar-first car.
The viewer therefore orders them 7–0 from travel-left to travel-right. The array
center is the gap between channels 3 and 4. The eight-channel profile has no
single middle sensor.

Only one contiguous group of 1–4 black channels supplies a centroid. No detection
is lost line; multiple groups are split/ambiguous; a group wider than four is
wide/ambiguous. `0x18` is a valid centered array observation; `0x81` and `0xFF`
cannot assert centering. Centering beneath the forward array alone cannot prove
that the axle lies on the line or that the vehicle heading follows the tangent.

Both controllers use positive error for tape to travel-left, including recovery.
A clean sample resets the measurement age. Ambiguous or missing input briefly
holds the last clean reading (80 ms), then uses the estimated position of the
forward array. A 20 ms filter and 0.35 m/s error slew bound prevent correction
jumps during loss and reacquisition. Planned untaped legs use odometry directly.
A clean-to-white endpoint candidate must start late in the planned arc and
remain white for 300 ms. This confirmation rejects a 250 ms late dropout while
allowing longitudinal odometry drift. Wide patterns need the estimated forward
array near the geometric endpoint; a broad ambiguous pattern in the middle
cannot skip the rest of the arc. Missing or ambiguous input never asserts
centering. Sustained loss near an endpoint remains optically indistinguishable
from leaving the tape; this policy uses route context rather than claiming an
extra observable signal.
Line-aided odometry projects the forward sensor point and the local track normal;
it does not treat the bar reading as an axle-origin measurement. Heading control
continues to use the IMU/odometry estimate, never MuJoCo ground truth.

`firmware/core/line.h` implements the same observation and recovery law, without
MMIO. `firmware/line_config.h` is generated from the Python profile by
`python -m race.fwconfig`. The production driver normalizes GPIO once. RAC2 keeps
its 64-byte layout: +0x20 reports the actual firmware-read mask; +0x30 adds source
in bits 16–17, raw observation in bits 18–19 and array centering in bit 20;
+0x38 is the applied steering error, which may be held or estimated.

## Reproduce the checks

Build the production ELF and the GPIO bring-up ELF, then run:

```text
python -m race.fwconfig
bash firmware/build_line.sh
bash firmware/race/build.sh
python -m unittest tests.test_firmware_line tests.test_line_tracking tests.test_race_cli -v
python -m unittest tests.test_race_firmware -v
cd web
npm run build
```

The GPIO bring-up runs the ARM driver and production line law on Renode. It checks
all 256 input patterns, active-low readback, invalid patterns, centering and a
loss/split/reacquisition sequence against Python. Results live at 0x2001ED00;
commands at 0x2001ED80, inside the linker's reserved SRAM carve.

The closed-loop regressions apply left/right yaw disturbances on arc entry,
250 ms and 1.8 s of missing digital input, 150 ms of split/wide detection,
and 250 ms of loss beginning at 82% arc progress. Each runs through
both controllers, must finish Task 2 with the existing ground-truth grader, and
checks correction continuity and actual consumed input. The longer loss also
exercises slowdown and search and must reacquire on the same arc. These are reproducible
software scenarios; they do not establish an unlimited capture envelope.

Local evidence for this change is collected in `output/line-fidelity/`.
The evidence includes source/ELF fingerprints. An earlier fixed snapshot was
used while the CAD and MCU models were being edited in parallel; the final
working-profile line cases are recorded separately so those results are not
silently attributed to a different vehicle geometry or balance calibration.

The current-profile GPIO checks cover all 256 masks and C/Python filter parity.
The public firmware-launch check confirms that the CLI-selected production ELF
actually reads the driven PF0–PF7 masks, with one heartbeat per coupling.
The peripheral backends cache the same GPIO receivers that the monitor invokes.
Their native `OnGPIO` calls preserve AF routing, digital levels, 20 us edge
spacing and the per-period counter check; they do not write CNT to emulate wheel
motion. The input-path regression compares monitor and native traces across
wrap/reversal, repeated levels, wrong AF/mode, disabled counting and cold reset.
The local timing probe measured 100 edges at 0.8333 s through the monitor and
0.1668 s through the native receiver. Those wall times are host measurements,
not assertions of silicon timing.
The viewer was checked on white floor, black tape, the centered 3/4 pair and a
disconnected server; disconnected data clears the live centering claim.

The frozen pre-RCC-gating profile is recorded as five mutually consistent green
records in `output/line-fidelity/` (each zero failures/errors/skips, with
unchanged source/ELF hashes; the per-file SHA-256 map is identical across all
five, pinning one vehicle geometry and balance calibration):

- `native-software-gates.json` -- 104 PASS: MCU driver guards, the 13 line-law
  tests, 3 CLI/input tests and all four Python missions.
- `native-twin-functions.json` -- 24 PASS: native balance/loop functions.
- `native-line-matrix.json` -- 14/14 PASS: the closed-loop disturbance matrix
  (left/right arc-entry yaw, 250 ms dropout, split, wide, late 250 ms dropout at
  82% progress, and 1.8 s loss exercising slowdown/search) on both controllers.
- `native-task4.json` -- peripheral task-4 e2e PASS at 119.199 s: four laps,
  16/16 nodes in order, 0.056 m stop error, both encoder counters wrap twice,
  heartbeat matches all 23,906 couplings.
- `native-race-peripheral-gates.json` -- task-1 lockstep, tasks 2/3 through the
  peripheral path, and the serial-during-mission gate, all PASS.

The later RCC-enable model is verified separately in
[rcc_status.md](rcc_status.md); these five records remain evidence for
their pinned pre-RCC model. The RCC change does not claim a new run of the
14-case disturbance matrix or the tasks 2/3 serial mission gate.

An earlier `final-integration-gates.json` (88 checks) belongs to a pre-line-tuning
snapshot and is superseded. A Python mission pass or a GPIO-law parity check is
not a substitute for the closed-loop matrix or the peripheral mission gates.

The 2026-09-30 documentation review updated only comments in
`stm32f4_pwm.c` and `stm32f4_pwm.h`, so those two working-tree source hashes
differ from the frozen evidence map. Rebuilding the race, balance and PWM
bring-up ELFs produced byte-identical binaries to that map (SHA-256
`410d161a8d3d193b730ea7e2501b5097cbc53e72eccfbef25ffcd97466b88259`,
`c03c3e1cf14588dc27dd2279b5f71ae9d97664e4f66f90b783d30bc58ac22d58`,
and `80f472692e42db01b1026c375bde75b8705ad1b0fcb502a0ae9f2c8d26d688f0`
respectively). The five test records still pin the exact source snapshot used
for runtime verification; the comment amendments do not alter those ELFs.

## Execution scope

The production peripheral path is implemented for the register sequences and
modes these drivers use. This is a bounded execution model, not a complete model
of arbitrary STM32 firmware. For example, the ADC's conversion now paces its
sample time (battery_status.md) but still has no analog front-end noise
slice; encoder timers support the driver's unfiltered x4 mode; the clock tree is
pinned to the 16 MHz reset profile; UART wire pacing and PWM within-period phase
are not faithful. The drive-chain decoder enforces PWM clock/enables/MOE/STBY,
and [rcc_status.md](rcc_status.md) adds RCC register/clock gating for the
firmware-used peripherals, including GPIOF. Unused peripherals and a full
clock tree remain outside that slice. The custom
watchdog now performs a machine reset, covered by the integration run; the older
statement that watchdog reset can only be checked on the board is superseded by
that model and its reset test. Real oscillator variation and watchdog register
update latency remain unmodeled.

## Unmeasured physical properties

The hardware is unavailable. Channel pitch (11 mm), optical footprint diameter
(3 mm), valid slant range (5–60 mm), thresholds (55%/45% black coverage), response
time and polarity must be checked against the purchased module. The current
coverage model is a deterministic geometric proxy; it does not model analog
reflectance, ambient light, LED current, surface gloss, comparator noise or
per-channel calibration. Illumination and indicator positions in the viewer are
diagnostic overlays, not an asserted manufacturing drawing of the bought part.

Firmware execution, digital observations and these recovery cases can be tested
now. Optical accuracy and physical steering margins require measured data; the
software profile remains explicitly labelled as assumed until then.
The disturbance matrix exercises the seven listed cases on Task 2 in each
backend; Task 4 has a clean full-mission peripheral gate. It does not prove
every dropout location on every route. The controller sees only the eight GPIO
bits, so an out-of-range optical spot is indistinguishable from white floor at
the firmware input; `valid_bits` is diagnostic simulator telemetry, not an
extra production sensor channel.
