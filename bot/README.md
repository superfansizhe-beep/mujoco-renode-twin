# bot/ — the vehicle + platform mechanics (what this car is, how it runs)

Three layers, one direction of dependency:

| Layer | Package | Owns |
|---|---|---|
| vehicle + platform | `bot/` (this package) | the car itself: mass table, motor model, IMU/encoder domains, MJCF physics (incl. the 8-way line-bar sample sites), LQR gains, the 200 Hz coupling loop, the controller slot, mailbox word packing, the state-frame schema, the ws server, the Renode channel |
| balance demo app | `twin/` | the demo riding the vehicle: mode/drive_duty defaults + `set_mode()`, `DriveController`, the TWN2 mailbox layout, `twin_fwconfig.h`, the balance firmware backend |
| exam app | `race/` | the smart-car exam on the same vehicle: track field, task registry, `RaceController`, the RAC2 mailbox, `race_fwconfig.h`, spawn poses, the exam firmware backend |

The contract that keeps it one car: apps import `bot`, never each other
(the race firmware's balance gains are `bot.backend`'s, via the same
generated `twin_fwconfig.h` the balance firmware compiles); there is ONE
MJCF (`bot/mjcf.py`) — race spawns on it bar-first instead of building a
model; state frames have one constructor (`bot/telemetry.py`) and one
server (`bot/server.py`, :8765 for twin, :8766 for race) feeding one web
viewer — each server opens the connection with a scene frame announcing
its app (race embeds the track payload, `race/scene.py`), so the viewer
switches UI modes from the protocol, not frame sniffing. `RaceLoop` and
`TwinLoop` are parallel subclasses of `BotLoop`.

## Modules

| Module | Responsibility |
|---|---|
| `mass_properties.py` | per-part mass table, every constant provenance-tagged (CITE/CALC/WEIGH/GUESS); geometry imports CAD constants |
| `motors.py` | duty→torque: two-point line through stall 0.57 N·m + no-load 320rpm + voltage derating |
| `sensors.py` | IMU raw-domain conversion (±2g/±250dps, low-pass matching the MPU6050 DLPF), encoder 1320/rev + `COUNTS_PER_M`; line-bar constants `N_LINE_SENSORS`/`LINE_PITCH` (GUESS, caliper pending) |
| `mjcf.py` | generates MJCF from CAD constants; sphere-contact wheels, trim keyframe; the CAD's 8-way line bar rides as eight massless sample sites (`line_0..line_7`) |
| `mailbox.py` | word-packing helpers (lo16/hi16/pair32/u32_to_i32, `MAGIC_RADAR`) + the base SensorFrame/MotorFrame payloads shared by every RAM contract |
| `backend.py` | `Controller` interface + LQR balance stub `BalanceController` (the gains the exam firmware includes) |
| `lqr.py` | numerical linearization over the coupling period + discrete DARE; gains derived from the bot itself |
| `loop.py` | `BotLoop`: 200Hz coupling + 1ms×5 substep zero-order hold (twin's `TwinLoop` and race's `RaceLoop` both inherit this base, swapping app/controller through small seams) |
| `telemetry.py` | single construction point for state frames: BASE_FIELDS + `pose_fields()` (speed = projection on the travel axis, positive nose-forward); both apps' frames come from here |
| `server.py` | `BotServer`: WebSocket 30Hz state broadcast + commands (nudge/reset/pause/mode/task) |
| `renode.py` | shared Renode channel: machine boot / word I/O / heartbeat wait (both firmware backends share it) |
| `periph.py` | the shared peripheral bench: STM32F407 bench/hardware map (IMU bench words, encoder timers, TIM1/RCC duty truth), `decode_duty_pair`, quadrature-edge + line injection helpers (both apps' Renode peripheral backends drive the same machine through it) |

## Coordinates and speed semantics (each pinned once, where)

- **Model frame = CAD frame**: X width, Y forward, Z up (`mjcf.py`; MuJoCo's
  −Z gravity agrees with the CAD with no rotation, so the web viewer
  consumes poses verbatim).
- **IMU signs**: +Z up, +X out the right side, +Y forward; accelerometer
  reads specific force (+1g at rest, like the real MPU6050), gyro about +X
  = pitch rate, positive = nose up (`sensors.py`, pinned by tests).
- **Drive sign chain**: + = forward (+Y); wheel hinge axes `(-1 0 0)` so
  positive joint angle/rate/torque, encoder counts and duty all mean
  forward on BOTH wheels (`loop.py`, pinned by tests).
- **`speed_mps`** = signed projection of world velocity on the chassis +Y
  axis, scaled by `travel_y` (+1 twin, −1 race) — positive = advancing
  nose-first (`telemetry.py`). Race runs the same chassis the other way
  round (bar-first, chassis −Y; full sign chain in race/README.md).
- **LQR state** `z = [y, ydot, theta−theta_ref, thetadot]` with
  `theta_ref` = `hover_trim_rad()` (CoM over the wheel-contact line,
  `mjcf.py`); gains recomputed by `lqr.py`, single source in
  `backend.py`.

## Facility entry points

```bash
.venv/Scripts/python.exe -m bot.lqr                                # re-derive LQR gains
.venv/Scripts/python.exe -m bot.mjcf output/twin/balance_bot.xml   # export the MJCF
```

Application entry points live with the apps: `python -m twin` (balance
demo, README in twin/) and `python -m race` (exam, README in race/).
