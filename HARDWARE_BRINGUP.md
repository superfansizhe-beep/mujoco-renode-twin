# Hardware Bring-up & Takeover Instructions

State at handover: repo at `d5e349e`, working tree clean, every gate green.
Sim evidence: five SHA-frozen records in `output/line-fidelity/` (104 software /
24 twin / 14-case line matrix / task-4 / race-mission, all pass, 121-file source
pins). CAD: 35/35 checks, `src/cad_modeling/ASSEMBLY.md` is the manufacturing
reference. This sheet indexes the real checklists; the `*-status.md` files stay
authoritative for their subsystems.

## 0. Ground rules

- Python is always `.venv\Scripts\python.exe` — never bare `python` (the
  System32 WSL launcher shadows Git Bash; the test suite passes the resolved
  executable for this reason).
- Gate commands, one **heavy** run at a time (a single Renode run is fine;
  two at once freeze the host):
  - `python -m unittest tests.test_race tests.test_race_firmware tests.test_firmware_board tests.test_firmware_imu tests.test_firmware_encoder tests.test_firmware_pwm` (now ~1 h — task-4 firmware laps are inside `tests.test_race_firmware`)
  - `python -m tests.test_twin` (function runner, own `main()`)
  - `python -m tests.test_assembly` (35 CAD checks, OCCT only)
- Generated headers: after touching `race/fwconfig.py`, `twin/fwconfig.py`,
  `bot/line_sensor.py`, or anything they import — regenerate with
  `python -m race.fwconfig` / `python -m twin.fwconfig`; `--check` must exit 0.
- Mass provenance tags (`CITE/CALC/WEIGH/GUESS` in `bot/mass_properties.py`):
  upgrade a tag when you physically measure; keep `total_mass()` inside the
  1.0–1.15 kg band; recompute K_LQR (`bot.lqr`, Q=(40,1,200,2), r=8) and
  regenerate `twin_fwconfig.h` whenever the mass table moves.
- Commits: atomic, explicit paths. On a tree co-edited by another session,
  grep the staged content for the other session's fingerprints before
  committing (whole files carry foreign hunks — this bit us once).
- Evidence shortcut: if the tree is byte-identical to a SHA-frozen green
  record, cite the record instead of re-running the gate.
- ELFs/maps are gitignored; build via `firmware/twin/build.sh` and
  `firmware/race/build.sh` (the suites do this themselves).

## Phase A — unbox, measure, backfill constants (no power)

| # | Measure | Expected / assumed | Update |
|---|---------|--------------------|--------|
| 1 | Motor: weigh; gearbox length; **output-shaft eccentricity** | 152–169 g (code 160); GEARBOX_L 24.2 mm confirms the 1:30 LR24; eccentricity: STEP says 7 mm, family drawing 5.5 mm — measure the bought variant | `WHEEL/MOTOR masses` in `bot/mass_properties.py`; `OUTPUT_SHAFT_OFFSET` in `src/cad_modeling/jgb37_520.py` (gearbox hangs below the shaft datum) |
| 2 | Wheel: D, width, hub bore, grub spec; weigh | D80×25 assumed; bore = SHAFT_D+0.2 clearance envelope; mass GUESS 100 g | `src/cad_modeling/wheel.py`, `WHEEL_MASS` |
| 3 | Bracket: PLATE_T, BASE_T; weigh | PLATE_T 4.0 is GUESS (2–3 mm expected) | `src/cad_modeling/bracket.py`; mass now CAD-volume × steel — recalibrate density if plated |
| 4 | Line bar: envelope, hole pattern, **channel pitch**; weigh | 91.11×36.5×13.5; Ø3 at ±8.055/±21.025; pitch assumed 11 mm; mass band 15–25 g (code 20) | profile in `bot/line_sensor.py` (flows into `line_config.h` via `race.fwconfig`); `LINE_BAR_MASS` |
| 5 | Battery: caliper, weigh, 1 kHz internal resistance | 106×34×22; 166–182 g; 25–35 mΩ | `BATTERY_MASS`; record IR for the future sag model |
| 6 | Driver + MCU boards: footprints, mounting patterns | PROVISIONAL ±8/±5 and ±15/±10 — **never drill a populated PCB to a placeholder pattern**; use a carrier if needed | `PCB_MOUNT_HOLES` in `src/cad_modeling/deck.py` |
| 7 | GY-521: outline + holes (quick check) | STEP-measured 20.35×15.65, D3 at (±8.175, +5.825) | only on disagreement |
| 8 | TB6612 module: silkscreen pinout vs PE0–PE4 mapping | — | `stm32f4_pwm.h` is the swap point |

After any constant edit, run the loop:

```
python -m cad_modeling.balance_bot   # regen STEP/GLB/DXF exports
python -m tests.test_assembly        # 35 checks
python -m twin.fwconfig              # regen trim/gains header
python -m tests.test_twin            # equilibrium at new trim + e2e
```

Power-chain reminder: 3S (11.1 V) → **buck to 5 V** → AMS1117 to 3.3 V. Never
feed 11.1 V straight into the AMS1117 (7.8 V drop overheats it).

## Phase B — electrical bring-up, safest-first

Each subsystem's complete table lives in its status doc; the critical rows:

1. **Rails before chips** — buck 5 V and 3.3 V metered under load; VREF+ is the
   same 3.3 V rail the ADC trusts (`firmware/battery_status.md`).
2. **UART link** (`firmware/uart_status.md`) — PA2→module RX, PA3←module TX,
   common GND; confirm 3.3 V logic (level-shift PA2 if a 5 V carrier); set the
   module AT-baud to 115200 8N1, or change `UART2_BAUDRATE`/`UART2_BRR`
   **together** (layout test pins the pair); real wire is ~87 µs/byte vs the
   1 ms TXE deadline; interactive check: `python -m twin.uart_session`.
3. **IMU** (`firmware/imu_status.md`) — WHO_AM_I 0x68 (AD0=GND); flash
   `imu_bringup.elf`, dump the trace ring at 0x2001F080 over SWD, byte-diff vs
   `GOLDEN_TRACE` in `tests/test_firmware_imu.py`; flat = az +1 g; SCL PB6 /
   SDA PB7 AF4 open-drain; unplug SDA → init must report the AF error and
   recover on replug.
4. **ADC / battery** (`firmware/battery_status.md`) — measure the divider; if
   not 30k:10k change `VBAT_DIVIDER` (`stm32f4_adc.h`) **and**
   `DefaultBatteryDivider` (`adc_model.cs`) together (layout test pins them
   equal); meter VREF and set `ADC_VREF_MV`; correlate cell-by-cell.
5. **PWM / TB6612** (`firmware/pwm_status.md`) — **stall-current risk first**:
   motor stall ≈3.2 A vs TB6612 1.2 A absolute continuous — first motor power-up
   on a current-limited supply; decide current limiting / stall timeout / driver
   swap before racing. Then: scope PWMA 20 kHz (clean 800-count sawtooth after
   MOE+STBY), per-phase truth table (IN1/IN2 → CW/CCW/brake/coast), swap IN pins
   if a wheel spins backward, +w = chassis +Y.
6. **Encoders** (`firmware/enc_status.md`) — with the wheel near CNT=0xFFFE,
   rotate forward through wrap and watch the position at 0x2001EE08 (debugger);
   repeat backward through zero; swap A/B on a motor that counts backward;
   3.3 V, pull-ups on.
7. **Line bar** (`firmware/line_status.md` + `race_status.md` BOARD rows) —
   confirm the bought board is the YB-MX04-2.0-class part and note the
   **interface** (8×IO vs I2C vs USART — a USART board replaces
   `stm32f4_line.c` with the UART driver and makes UART a control input);
   polarity over white/black with a meter → `LINE_SENSORS_ACTIVE_LOW`
   (`stm32f4_line.h`) and the shared `ACTIVE_LOW` in `bot/line_sensor.py`
   change **together**; sweep black tape to verify channel order (i → PF i,
   growing +x) and caliper the pitch vs 11 mm; sensing face sits ~8.4–10 mm
   (window 5–60 mm); module output HIGH may be 5 V — PF0–7 must be the
   FT (5 V-tolerant) pins or get series resistors; **check the datasheet
   before wiring**.
8. **IWDG** (`race_status.md`, `stm32f4_iwdg.c`) — meter the real LSI; a
   deliberate hang must reset with the drive chain dead (coast); note
   register-update latency vs the timed-out reset.
9. **Boot rule** — reserve ≥20 s line-bar stabilization before the first
   auto-calibration (module manual).

## Phase C — correlation and the taped field

- The board runs the SAME production ELFs as the sim (one-image equivalence
  program, `firmware/README.md`): bring-up ELFs first, then `twin` and `race`
  production images; acceptance = the same declared gates, measured.
- Field days: tasks 1–4 on the taped sheet with the grader's stopwatch,
  node-beep placement and stop-distance measurement (`race_status.md`).
- Record measured actuals back into the `*-status.md` tables and flip SIM
  labels to BOARD-verified; the battery OCV-SOC/IR numbers become the input of
  the future voltage-sag model.

## Phase D — sim-side open items (no hardware needed)

From the verified gap table (2026-09-29); P0 (drive-chain gating + IWDG
expiry) already landed in `bb5c378`. Criterion for closing any gap: *when
firmware changes a clock enable, pin mapping, output enable or deadline, the
sim must produce the corresponding behavior or failure.*

- **P1 RCC enable gating** — probe Renode 1.17's clock API before modeling;
  the repl deliberately pins the 16 MHz HSI tree (a future clock-init milestone
  owns frequency derivation — gating is separable).
- **P1 MPU ranges** — `mpu6050_model.cs` stores FS_SEL/AFS_SEL but does not
  apply them; a wrong range must yield wrong scaling in sim.
- **P1 UART wire time / ORE** — TX is instantaneous in the model; add ~87
  µs/byte pacing and overrun behavior.
- **P2** — encoder AF path beyond the guarded pins (fallback: pin AFRL nibbles
  in the config gates), ADC conversion latency (bundle with the battery-sag
  model), I2C NACK oracle.
- Discipline: every fidelity addition lands WITH its negative gate and an
  RM0090 clause citation; probe before modeling; don't model what the firmware
  does not use.

## Gotchas

- The 1.8 mm counterbore assumes 3 mm stock — do not reuse it in thinner plate.
- Battery leads, connector and buckle are unmodeled; keep them in the side
  corridors; the retained pack has 4 mm below the upper disc — never compress
  it against the plate.
- A cancelled Renode run keeps burning a core (`pyrenode3` hosts .NET
  in-process): find the python PID by CPU-seconds and `Stop-Process -Force`;
  never kill the idle 0-CPU pythons another session left.
- `output/` is gitignored scratch — evidence worth keeping (probe logs, gate
  records) should be cited by path in the status docs; consider tracking
  `output/peripheral-review*/` if that evidence matters long-term.
