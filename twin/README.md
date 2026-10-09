# twin/ — the balance demo app on the bot/ stack (phase 1: mailbox-stub controller; phase 2: Renode C firmware takes over)

The vehicle + platform mechanics (physics model, sensors, LQR, coupling
loop, telemetry, ws server) live one level down in `bot/` — see
`../bot/README.md`; this package is the demo application riding it.
Peripherals to simulate (IMU/encoders/motors) are wired into the MuJoCo
physics sim as RAM-mailbox stubs. Phase 1: the Python stub controller
closes the loop end to end, web frontend for the live view; phase 2
`RenodeFirmwareBackend` swaps the stub for **real C firmware running in
Renode** (`firmware/twin/main.c`, line-for-line isomorphic with the stub, A/B
comparison measured a trajectory delta of 0.00°/0.0cm),
one switch with `--backend renode`; the stub stays as the reference and
regression baseline.

Board-driver policy: [HAL/LL inclusion gate](../firmware/README.md). Keep the
register drivers through the Renode phase; revisit one peripheral only after
its existing bring-up fails on physical hardware, preserving the board API.

## Running

```bash
# balance demo + web view (two terminals recommended)
.venv/Scripts/python.exe -m twin --balance --serve --realtime
cd web && npm run dev            # opens http://localhost:5173
# the same viewer also runs race: python -m race --task 2 --serve --realtime,
# open http://localhost:5173/?ws=ws://127.0.0.1:8766 (track 3D loads automatically)

# phase 2: C firmware in Renode drives the same bot (needs [renode] extra + local portable build)
.venv/Scripts/python.exe -m twin --balance --serve --realtime --backend renode

# hands-on serial link: firmware in Renode + telnet as the Bluetooth far end
.venv/Scripts/python.exe -m twin.uart_session            # then: telnet localhost 4545
.venv/Scripts/python.exe -m twin.uart_session --gdb 3333 # + arm-none-eabi-gdb -ex 'target remote :3333'
# the PRODUCTION balance ELF with live telemetry (bench fed the at-trim rest frame):
.venv/Scripts/python.exe -m twin.uart_session --elf firmware/twin/balance_fw.elf --bench-imu

# headless regression
.venv/Scripts/python.exe -m tests.test_twin        # 25 items (auto-SKIP when the firmware e2e environment is missing)
.venv/Scripts/python.exe -m tests.test_assembly    # 26 CAD items

# misc
.venv/Scripts/python.exe -m twin --drive --duty 300 --seconds 2   # link check
.venv/Scripts/python.exe -m bot.lqr                               # re-derive LQR gains
.venv/Scripts/python.exe -m twin.fwconfig                         # regenerate firmware/twin/twin_fwconfig.h
bash firmware/twin/build.sh                                           # build firmware (artifact balance_fw.elf)
.venv/Scripts/python.exe -m twin.renode_smoke                     # mailbox address smoke test
.venv/Scripts/python.exe -m bot.mjcf output/twin/balance_bot.xml  # export MJCF
```

## Structure

The vehicle stack (mass table, motors, sensors, mjcf, mailbox helpers,
controllers, lqr, `BotLoop`, telemetry, server, Renode channel) lives in
`bot/` — module map, coordinates and facility entry points in
`../bot/README.md`. This package keeps what belongs to the demo app:

| Module | Responsibility |
|---|---|
| `loop.py` | `TwinLoop(BotLoop)`: the demo app's mode/drive_duty defaults + `make_backend()` factory + `set_mode()` runtime swap |
| `backend.py` | the demo app's own controllers: constant-duty drive check + the `make_backend()` mode picker (interface + balance stub live in `bot/backend.py`) |
| `mailbox.py` | TWN2 RAM contract (see below); frame types + word helpers single-sourced from `bot/mailbox.py`; Python stub and Renode backend share the packing |
| `fwconfig.py` | generates `firmware/twin/twin_fwconfig.h` (single source of constants, hand-copying forbidden) |
| `renode_backend.py` | phase-2 backend: drives the firmware in-process via pyrenode3 (channel in `bot/renode.py`) |
| `renode_smoke.py` | write/read round-trip of the mailbox addresses on the Renode F407 sysbus |
| `uart_session.py` | hands-on serial-link session: firmware in Renode with a TCP socket as the Bluetooth module's far end (`telnet localhost 4545`), optional `--gdb`; `--elf firmware/twin/balance_fw.elf --bench-imu` runs the PRODUCTION ELF with live telemetry; the CI-side bridge is the TerminalTester in [tests/test_firmware_uart.py](../tests/test_firmware_uart.py) + the production gate in [tests/test_twin.py](../tests/test_twin.py) -- gates and board labels in [firmware/uart_status.md](../firmware/uart_status.md) |

Phase 2 adds `firmware/twin/` (`main.c` / `mailbox.h` / `twin_fwconfig.h` (generated) /
`build.sh`; the *.elf/*.map artifacts are untracked --
`bash firmware/twin/build.sh` before `--backend renode`; the board files
`stm32f407.ld`/`stm32f407zg.repl` stay shared at `firmware/` root).

## mailbox v2 contract (any layout change must bump the magic)

Window `0x2001FFC0..0x2001FFFF`: **top of the F407's real 128K SRAM** (the
radar exam's 0x2003FFF0 exists only in Renode's generous sysbus, not on a real
chip; this contract must run on a board you can buy). The firmware linker
script shortens SRAM to `LENGTH=0x1FFC0` to stay clear of it.
`firmware/twin/mailbox.h` is the C mirror of this table; tests cross-check it
**byte for byte**.

| Offset | Type | Content | Direction |
|---|---|---|---|
| +0x00 | u32 | magic `TWN2` (v1 was `TWNB`; the v2 layout change bumps the magic per the rule) | — |
| +0x04 | u32 | seq (firmware waits for a change = data ready; emulates the IMU ODR of 200Hz) | harness→firmware |
| +0x08 | i16×3 | accel raw (±2g domain) | harness→firmware |
| +0x0E | i16×3 | gyro raw (±250dps domain) | harness→firmware |
| +0x14 | i16 | temp raw (degC=raw/340+36.53) | harness→firmware |
| +0x16 | u16 | battery mV | harness→firmware |
| +0x18/0x1C | i32 | encoder cumulative counts (1320/rev, +=forward) | harness→firmware |
| +0x20/0x22 | i16 | duty_l/r (‰, ±1000, +=forward) | firmware→harness |
| +0x24 | u32 | fw_seq heartbeat (+1 per control cycle; harness judges firmware alive/dead) | firmware→harness |

## Phase 2: Renode takes over (pyrenode3 channel)

The channel is **pyrenode3** (Antmicro's official Python bindings, installed
with `uv add --optional renode` then `uv sync --extra renode`): via pythonnet
it loads Renode **in-process** as a .NET assembly. `PYRENODE_PATH` points at
the .NET-flavored Renode (on this machine it defaults to renode-mcu-survey's
renode_1.17.0-portable). Measured 2026-09-28 (5ms virtual step):

| Channel | Wall clock/step | Realtime ratio @200Hz |
|---|---|---|
| TCP monitor (radar era) | ~200 ms | ~0.05× |
| pyrenode3 monitor commands | ~19 ms | 0.26× |
| **pyrenode3 direct .NET calls** (`Emulation.RunFor(TimeInterval)` + direct sysbus write/read) | **~6 ms** | **0.84×** |

- Firmware `firmware/twin/main.c` is **line-for-line isomorphic** with the stub
  (same raw-domain scaling, same filter, same LQR gains, same clamps);
  constants are all generated by `twin.fwconfig` (a stale `twin_fwconfig.h`
  fails the tests). Battery voltage is read live from the mailbox, truer than
  the stub's fixed 11.1V.
- **The A/B comparison is the porting-correctness proof**: under identical
  conditions the stub vs firmware trajectory delta measured 0.00°/0.0cm
  (covering the whole kick-recovery). Test tolerance 1°/3cm leaves margin.
- Heartbeat rate = coupling rate: over 200 coupling cycles fw_seq gains
  exactly +200 (pinned by tests); dropped frames surface immediately.
- **Real-board migration**: swap the three mailbox read/write groups for
  MPU6050 I2C reads, encoder timer reads, and PWM duty writes; the control
  core (raw→SI→filter→LQR→duty) carries over as-is; the two headers stay
  untouched. SysTick not needed — the seq strobe is the clock.
- Firmware build: arm-none-eabi-gcc, hard-float M4F
  (FPU enabled in Reset_Handler, see troubleshooting);
  `SOFT=1 bash firmware/twin/build.sh` switches to soft float — the control core
  is ~50 flop/cycle, performance is irrelevant.

Sign conventions across the chain (**+ = forward (+Y)**, wheel hinge
axis `-1 0 0`, positive angle/torque/count/duty = forward on both
wheels) are pinned once in `../bot/README.md`.

## Known approximations (explicitly recorded)

- **Inertia** = lumped approximation of primitive bodies (MuJoCo sums explicit
  geom masses); exact CAD inertia export is a later upgrade.
- **Wheel contact geometry = sphere** (radius = tire radius): a rigid
  cylinder/ellipsoid contacts at the rim as soon as it tilts, and the contact
  point shifts sideways by "curvature radius × tilt" (here 128mm×1°; a real
  rounded tire only ~3mm×1°), effectively inventing a wide support patch out
  of thin air — the drive demo once parked on a "rim + tail skid" tripod
  because of this. A sphere's contact point always sits directly below the
  wheel center, zero drift; this is the standard approach for a simulated
  balance bot.
- **Trim angle (current mass table −16.7°)**: the hover condition is CoM
  directly above the **wheel contact point** (which moves with the axle), so
  the lever arm = com_z−AXLE_Z≈17mm, not the 57mm to the ground origin — v1
  used the wrong lever, computed −3.7°, and every closed loop quietly settled
  at the wrong −12°. The keyframe is placed at trim angle + exact z
  compensation (the true qacc=0 equilibrium); `hover_trim_rad()` derives it
  automatically from the mass table (with the 3S battery the tail-heavy trim
  is deeper; battery/part changes are followed automatically).
- **The motor datasheet is not self-consistent** (Kt back-derived from stall
  current vs Ke back-derived from no-load speed differ by 2×); the torque
  model fits its line through the two most reliable points (stall/no-load)
  and drops the current point.
- **armature 2.7e-4 kg·m²**: gearbox-reflected rotor inertia
  (rotor ~3 g·cm²×30²); without it the dumb torque source spins the 100g
  wheel up to slip instantly.
- Battery settled on **3S LiPo 2200mAh** (11.1V nominal ≈ motor rating;
  `--battery 2s` still simulates the derated run); the IMU
  has no noise/bias (the low-pass only damps MuJoCo soft-contact ringing);
  coupling rate 200Hz = the declared ODR. The 450‰ duty cap is bounded by
  ground traction (μ·N·R≈0.25 N·m/wheel), not by motor stall.
- Wheel D80×25 is still GUESS (not selected/unweighed; once the wheel
  arrives, backfill `wheel.py` and re-derive gains with `python -m bot.lqr`).

## Tuning/troubleshooting quick reference (every item actually hit this round)

- MuJoCo's `accelerometer` outputs **specific force** (+1g at rest, 0 in free
  fall), same semantics as a real MPU6050 — do not add a gravity correction
  on top (one was stacked on once, summing to 2g; the atan2 ratio was
  unchanged, so the filtered angle kept "looking right").
- compiler defaults to `angle="degree"`: writing radians in euler requires
  declaring `<compiler angle="radian"/>` (a wheel given 1.57° instead of 90°
  is a flat lying disc).
- Soft-contact ringing injects ±g-level accelerometer noise at the solref
  frequency → the IMU model carries a 25Hz first-order low-pass (the
  counterpart of the real chip's DLPF) + `integrator="implicitfast"`.
- Hand-tuned PD has **no fixed point** on a wheeled inverted pendulum
  (constant tilt→constant torque→constant acceleration, drifts forever);
  LQR is derived from the twin's own linearization (`lqr.py`) — re-derive
  after changing the mass table.
- **The FPU enable must precede any FPU instruction — including the `vpush`
  the compiler inserts into the main prologue**. Even the top of main's body
  is too late (measured: the first vpush took a UsageFault, PC dumped into
  Default_Handler); the correct spot is in Reset_Handler right after the
  `.bss` clear (same as ARM's official startup), see `firmware/twin/main.c`.
- **Both sides of an A/B comparison must run a symmetric timeline**: give one
  side an extra second of settle and the kick lands on a different system
  state, diverging to ±7° with no relation to porting correctness (hit for
  real in the first test version). Comparison tolerance = symmetric measured
  delta (0.00°) + margin (1°), never a guessed value.
- Complementary filter time constant dt/(1−α)=0.25s=50 frames: during
  bring-up, after feeding 20 frames the duty seemed not zeroed — the filter
  was still converging (first sample seeds from the gravity vector, then each
  frame pulls only 2%).
- **HUD shows "offline" but the connection dot is green**: the tab is in the
  background — the browser freezes requestAnimationFrame for hidden pages,
  and HUD/watchdog both live in the rAF loop; the WS itself is alive (the
  green dot is onopen writing the DOM directly). Switching back to the
  foreground restores it; not a server or code problem (this was the lingering
  phase-1 mystery, located on the spot 2026-09-28).
