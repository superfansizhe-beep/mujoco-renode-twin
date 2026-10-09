# race/ — Smart-car exam twin (balance bot + 8-channel line-follow bar, MuJoCo)

Full simulation of the 2024 national contest H-sheet exam ("auto-driving
smart car", the club exam's source paper): **the vehicle is the balance
bot itself** —
the 8-channel IR line-follow bar mounted in CAD long ago
(`cad_modeling.sensors` LINE_BAR_*, mass-table line_bar entries) is
promoted to primary sensor in this exam. The field is the sheet's own:
two symmetric R40 arcs and nothing else taped — every straight leg is
dead reckoning. **The platform stack is reused single-source from
`bot/`**: coupling loop (`RaceLoop` extends `BotLoop`), state-frame
schema (`bot/telemetry.py`), ws state stream (`bot/server.py`), Renode
channel (`bot/renode.py`), 3D web view (`web/`); this package only adds
the track geometry, the line-follow/task firmware logic, and the RAC2
layout.

Board-driver policy: [HAL/LL inclusion gate](../firmware/README.md). Keep the
register drivers through the Renode phase; revisit one peripheral only after
its existing bring-up fails on physical hardware, preserving the board API.

## Running

```bash
# demo: 3D live view (task 2, real-time pacing; two terminals)
.venv/Scripts/python.exe -m race --task 2 --serve --realtime
cd web && npm run dev
#   open http://localhost:5173/?ws=ws://127.0.0.1:8766
#   page buttons switch task 1-4 / pause / reset; a finished run shows
#   its grade banner (pass/fail + time + stop distance) until the next
#   task/reset; after a run ends it stays online for a rerun, Ctrl+C
#   exits

# headless exam (grades as soon as the run ends, JSON output; host-C fast mode by default)
.venv/Scripts/python.exe -m race --task 3 --verbose
.venv/Scripts/python.exe -m race --all              # scorecard for tasks 1-4
.venv/Scripts/python.exe -m race --task 2 --no-turbo --backend stub  # explicit slow/reference run

# real firmware in the loop (needs [renode] extra + a built race_fw.elf -- bash firmware/race/build.sh)
.venv/Scripts/python.exe -m race --task 1 --backend renode
.venv/Scripts/python.exe -m race.ab_probe 1 4      # stub vs firmware cycle-by-cycle comparison

# regression
.venv/Scripts/python.exe -m tests.test_race         # 27 items (incl. four-task integration)
RACE_SKIP_INT=1 ... -m tests.test_race              # quick unit tests only
.venv/Scripts/python.exe -m unittest tests.test_race_firmware   # peripheral firmware e2e: all four tasks; task-1 lockstep, task-4 wrap + full grade
.venv/Scripts/python.exe -u -m tests.encoder_wrap_probe         # +/-70000 counts through the production coupling protocol

# driving speed in world time, with host throughput reported separately
.venv/Scripts/python.exe -m race.speed_probe --backend renode --task 4 --output output/race-speed.json
.venv/Scripts/python.exe -m race.speed_probe --backend renode --task 4 --stress --output output/race-speed-stress.json
```

## Track (race/track.py, SI meters, origin = bottom-left of the field)

The **2024 national contest H sheet** field ("auto-driving smart car"):
220×120 cm with
**only two symmetric R40 guide arcs taped** (18 mm, black) — the sheet
bans any other marks. Nodes = the arc endpoints: A(60,100) B(160,100)
C(160,20) D(60,20), 20 cm margins all round. The figure's dimensions
each land once: 40+40 = arc radii, 100 = A–B gap, 60+60 = arc centers
to the field edges, 120/220 = the field. **Every straight leg of every
task (AB, CD and the AC/BD figure-8 diagonals) is untaped** — the exam's
core skill is gyro+encoder dead reckoning across open white, with the
bar meeting tape only on the arcs. Route lengths: task 2 451.33 cm,
tasks 3/4 507.45 cm per lap (pinned by tests). The old twin field (an
asymmetric R40/R60 egg with taped diagonals crossing at a tape X) was a
misreading of the sheet's figure and is gone.

## Structure

| Module | Responsibility |
|---|---|
| `track.py` | pure field: nodes / the two taped arcs + four untaped legs, (s, lat, ψ) projection, tape mask -- knows nothing about tasks |
| `tasks.py` | exam-paper side: `TASKS` registry (id/title/limit/laps/legs over field segments); route = legs×laps, so "task 4 = crossed ×4" is data; task_spec/route_length derived |
| `mailbox.py` | RAC2 contract ('RAC2'≠'TWN2'/'TWIN'): twin v2 superset + line_bits/task + buzzer/LED/task telemetry words; word helpers single-sourced from `bot/` |
| `spawn.py` | spawn pose only (car axis line on node A, tangent of the first leg; the bar starts over open white -- the run opens in dead reckoning); the 8 line-follow sampling sites are native in `bot/mjcf.py` (pitch/count: `bot/sensors.py`) |
| `controller.py` | exam firmware stub: sees only the RAC2 frame. Balance (bot LQR + moving reference) + steering (arc legs: bar PID + curvature feedforward + yaw-rate damping; **blind legs: heading hold on the leg tangent + odometry cross-track at full cruise**) + task state machine (node beep/LED, lap count, brake decision) |
| `loop.py` | `RaceLoop(BotLoop)`: swaps in the arena (spawn/bar read/task slots) + gt() probe + grade(); coupling discipline/drivers/state frame (`bot/telemetry.py`, travel_y=−1) all inherited |
| `renode_backend.py` | firmware backend: real C firmware in the controller slot (channel = `bot/renode.py`), synthesizes events/telemetry from RAC2 status words; `uart_telemetry=True` attaches the pre-boot TX tap + write-only tester on usart2 (twin rule) |
| `fwconfig.py` | generates `firmware/race/race_fwconfig.h` (includes the twin header; route tables baked per task from the `tasks.py` registry as travel-frame records) |
| `ab_probe.py` | stub vs firmware per-cycle duty delta + gt drift comparison (porting-correctness instrument, not a test) |
| `../tests/test_race_firmware.py` | peripheral firmware e2e: task-1 lockstep (events equal, gt <3 cm, grade PASS, heartbeat +100/100), tasks 2-3 full grade, task 4 four laps + encoder wrap + full grade in a 150 s budget, the serial-link gate (v3 shell: telemetry/node/done lines + commands mid-mission through the TX tap) (real unittest skip without the env) |
| `scene.py` | the `--serve` scene frame's track payload: field + tasks composed for the viewer from `track.py`/`tasks.py` -- the canvas and the grader share one source, nothing exported by hand |
| `bot/server.py` (reused) | ws :8766 state stream (`--serve` starts `BotServer(port=8766, scene=...)` from `race/__main__`; the scene frame is each client's first message) |
| `web/` (reused) | the 3D view is the twin viewer: `?ws=...:8766` (or `bot.ws()` in the console) switches to race; the track 3D data rides the scene frame |
| `../tests/test_race.py` | 27 items: geometry pins the exam sheet's numbers, tape mask (arcs only), task-registry coherence, scene payload composition, mailbox round-trip, state protocol pinned, four-task headless integration |

**Coordinate chain** (single source for the controller's signs): travel
direction = chassis −Y (line bar leads, sonar trails); chassis +X = left of
travel; +lat/+e = tape on the left of travel; +ψ = counterclockwise in the
world; CCW steering = more force on wheel_r (the chassis +X side wheel).
Encoder/duty stay in the bot's chassis frame (+ = chassis +Y = **behind**
travel, hence the minus signs all over the reversals).

## Grading rules (grade, self-set, explicitly recorded)

The exam only gives time limits and "beep/light on passing points / stop at
A", no quantified radius: the beep uses a **node zone of 0.30 m** (the finish
line is designed with lead, so it beeps ~0.3 m early, to land the braking
glide inside the window), stopping uses 0.30 m, reversing is an instant fail.
Task 4 is the timed event (`limit_s: None`): within_limit means FINISHED --
the elapsed time is the ranking number, not a cap.
Each event carries the ground-truth distance (annotated harness-side; the
controller never sees ground truth).

## bring-up log (every number was actually hit)

Mechanisms that carried over from the taped-field twin:

- **Semicircle projection wraparound**: a point 10 cm behind the node wraps to
  the arc's "far end", so at the B→C switch the feedforward fed point C's
  heading/curvature for 0.5 s — out-of-range projections must clamp to the
  nearer end by angular distance.
- **Dead trigger condition**: `s >= len+0.02` is always false (project itself
  clamps at len); with 0.3 m odometry drift the task wedges on the BC segment
  with the arc feedforward firing forever — saturation means "node already
  passed".
- **Recovery-mode signs**: on tape, +e = tape on the left → turn left; after
  line loss, +lat = the **car** on the left of the path → turn right. Same
  sign = correcting the wrong way, circling forever.
- **Differential must not eat the common-mode margin**: steering saturation
  pins one wheel at ±450‰ and starves balance. Differential gets its own slew
  limit: a ±5.5 mm bar quantization flips ±150‰ per 100 ms, enough to lever
  the WIP past the unrecoverable tilt point while accelerating.
- **Yaw-rate damping must wrap the feedforward**: damping the absolute yaw
  rate damps the arc's steady-state turn; damping (ω−ω_ff) is correct.
- **Odometry**: sphere-wheel steering scrub → longitudinal over-count on arcs
  (SCRUB_K compensates); while the bar is on tape, the lateral measurement
  continuously corrects lateral (ODO_K); full resync at nodes. Gating the
  scrub discount to on-tape cycles was tried for the blind legs and REVERTED
  — the churny node corners then corrupt the arc bookkeeping both ways.
- **Speed tracking**: the bot's stationary LQR used to chase speed
  limit-cycles — moving reference + one-sided leak governor; braking uses a
  steeper down-slope.
- **In-place head whipping**: after stopping, the rate servo chasing the
  stationary wobble forms a ±0.65 rad/s relay loop — the brake/complete
  differential goes straight to zero, letting yaw friction finish the settle.

The 2026-09-28 field rebase (taped egg → the sheet's arcs-only field)
rewrote the exam's difficulty profile: the straights are now open white,
so every straight leg is planned blind flight and the controller must
survive its own dead reckoning. The chain, in the order it broke:

- **Blind legs are the plan, not a failure**: creep/sweep/park timers must
  not fire while a leg's own geometry says "no tape here" (`seg.taped`
  gates all of them); a leg's darkness also must not pre-arm the next
  leg's park timer (lost_t resets at every node — task 4's lap-4 C died
  with AC's 5.7 s of dark on the clock).
- **Cruise overspeed is fatal on open white**: at 0.35 m/s the WIP runs
  +0.1–0.15 above plan with duty railed backward; on tape the bar ate the
  resulting yaw churn, blind it lands the car 15 cm off the next node
  (task-2 D). 0.28 m/s is inside the stable band; "turbo" rides the same
  envelope for now.
- **The yaw integral must be tilt-compensated**: ψ̇ = ω_z/cosθ — the body
  gyro under-reads ~4.3%/rad at the 16.7° trim, which is ~8° over a
  180° arc. Uncompensated, the car exited C a true 11° off the tangent
  while the estimate said on-tangent, then drove the blind CD leg into
  open field.
- **Node resync repositions, never re-heads**: snapping ψ to the sheet
  tangent at a node lies whenever the car crosses off-tangent, and the
  lie runs straight down the next blind leg. The honest integral + the
  post-node align servo turns the car onto the new tangent for real. (A
  conditional re-anchor on clean tape crossings was tried and REVERTED —
  the tangent-vs-body lag it re-injects cost task 4 its first D entry.)
- **The finish may be dead-reckoned on a dark arc tail**: the fresh-odo
  window is 2 s, not 1 — task 2 sagged off the DA tape mid-arc with a
  healthy odometry and the tighter gate refused the final-A line until
  the park timer ended the run.
- **The braking reference must follow the coast**: sustained overspeed
  leaves the car ahead of its station (y more negative than y_ref), and
  holding that station reverses the car a third of a meter back past the
  node (task-1 stop 0.305 vs the 0.30 window). While braking the
  reference walks down at 0.30 m/s to where the car actually stops.
- **A rate filter can feed the relay it guards** (2026-09-29, task 4):
  the 10 Hz yaw-rate lowpass lagged into the steering servo's ~8 Hz slew
  relay, and the relay's phase with the tilt filter's lag leaked a DC
  term into psi = integral(w/cos(theta)) -- ~3 deg/lap, fatal by lap 4.
  16 Hz halves it and 4 laps pass with margin; the integral itself is
  honest (probe: 0.36 deg over a full arc).

## Speed measurement (2026-10-01)

The owner confirmed JGB37-520 motors with 1:30 gearing, 80 mm wheels and
a 3S battery (11.1 V nominal). Tuning uses those existing plant parameters,
the 5 ms control period and the 450-permille duty cap. The balance gains,
physics step and peripheral drivers remain the same.

The selected turbo targets are 0.28 m/s on straights, 0.26 m/s on R40 bends
and 0.20 m/s near nodes. The yaw-rate filter moves from 16 to 40 Hz to retain
tracking margin with an additional actuator delay. Raising the straight
target to 0.30-0.32 m/s saved less than 0.1 s in comparable host-C trials;
0.30-0.35 m/s bend trials lost the route. This is the validated profile,
not a claim about the motor's mechanical top speed.

| Renode task 4 | Earlier profile | Tuned profile |
| --- | ---: | ---: |
| Bend target | 0.17 m/s | 0.26 m/s |
| Four-lap world driving time, arming excluded | 119.230 s | 95.865 s |
| Node sequence | 16/16 | 16/16 |
| Stop error | 0.056 m | 0.019 m |

The nominal run uses 19.6% less world driving time. Median measured body
speed is 0.28775 m/s on straight segments and 0.2682 m/s on bends; the means
are lower because those samples include node alignment, slowdown and line
recovery. Both encoder counters wrap twice, with 19233/19233 heartbeats and
couplings. Final stopped-body peak speed is 0.0071 m/s during the 450 ms
hold. The baseline arming interval was derived from its frozen 5 ms C
cycles; the new probe records the phase transition directly.

`race.speed_probe` reports actual body speed from the plant, the complete
mission grade, stopped-body motion, encoder wraps and one heartbeat per
coupling. Its driving-time denominator is MuJoCo world time, excluding the
initial arming interval for `world_mission_s`. Host computation is reported
separately as `wall_s`, `host_cpu_s` and real-time factor. Subtracting host
CPU time from wall time would give the wrong driving speed: simulation time
already excludes that slowdown. Sensor, MCU and actuator delays stay in the
loop. `--stress` adds a full 5 ms actuator hold, 10.5 V supply, lower floor
friction and a small shove at 10 s; these are simulation margin checks.

The combined Renode stress case passes in 101.320 s of world driving time,
with all 16 nodes, 0.031 m stop error, 20324/20324 heartbeats and two wraps
per wheel. Actual stopped-body peak speed is 0.0279 m/s with only 2.5 mm
of longitudinal motion during the hold. Source hashes, rejected candidates,
full mission records and focused checks are retained in
[speed-tuning-20261001.json](../firmware/evidence/speed-tuning-20261001.json).

The stopped check uses a 10 Hz filtered encoder velocity. Raw encoder deltas
still drive balance and odometry; the 0.03 m/s threshold, yaw threshold and
450 ms hold remain the same. The regression checks actual body motion during
that hold so encoder filtering cannot pass continued driving as a stop.
The speed constants originate in `race/controller.py`; regenerate the C
header with `python -m race.fwconfig` and check it with `--check`.

Renode results verify the production ELF through modeled peripherals. They
do not establish a physical top speed: motor current and driver temperature,
pack sag, tire contact, optical sensor behavior and board timing still need
measurement on the assembled car.

## Backend monitoring and event stream

Monitoring runs in the backend; the viewer has no diagnostic panel or serial
controls. Normal state frames contain pose, mission and line-sensor data,
without C symbol reads or the diagnostic event history. Record transitions
without adding diagnostic traffic to the viewer:

```powershell
.venv\Scripts\python.exe -m race --task 4 --backend renode --serve --serial-debug --event-log output/race-events.jsonl
```

```powershell
Get-Content output/race-events.jsonl -Wait
```

For backend inspection, add `--monitor-stream` to the server command, then
use this terminal client in a second shell. It prints JSON and requires no
viewer. Redirect `inspect` output to a file for further analysis.

```powershell
.venv\Scripts\python.exe -m race.monitor events
.venv\Scripts\python.exe -m race.monitor inspect
.venv\Scripts\python.exe -m race.monitor snapshot
.venv\Scripts\python.exe -m race.monitor ping
.venv\Scripts\python.exe -m race.monitor stat
.venv\Scripts\python.exe -m race.monitor pause
.venv\Scripts\python.exe -m race.monitor run
```

`--url ws://127.0.0.1:PORT` selects another backend; `events --duration 10`
bounds capture in wall seconds. `--monitor-stream` is opt-in for a whole
server session: all clients on that port receive the additional `state.debug`
fields, although the viewer ignores them. Leave it off for normal viewing.
The client skips replay frames and reports missing retained history. A saved
snapshot always includes full diagnostics, even when the stream is disabled;
the backend command is `{"type":"snapshot"}` and the file is written under
`output/race-debug/`. The terminal client reports its path after the save.

Estimation fields come from the Python reference or the loaded C binary's
actual symbols. Missing/stripped/mismatched symbols report `unavailable`;
simulator truth never fills an estimate field. The C ELF and 200 Hz control
path are unchanged by these reads. `--serial-debug` attaches before boot and
captures existing 10 Hz `T` lines and UP/node/done/starved/resume/pong events.
Ping/stat replies are identified in the event stream. Commands are queued
one byte per normal coupled step, so the CPU never advances without the
plant; resume before requesting a serial reply. No extra periodic serial
emission was added. Capture keeps at most 64 KiB of raw TX, 32 serial events
and the latest T line; commands cannot accumulate a backlog.

Every `state.debug` payload has schema 1, a fresh `run_id` per reset, monotonic
event `seq`, `first_seq`, `last_seq`, `dropped_events`, and a 64-event ring.
Phase/segment changes, mission nodes, sustained line recovery, sustained
PWM saturation, heartbeat gaps, faults, pause/resume and UART events survive
latest-frame coalescing. Untaped route legs do not trigger recovery alerts.
The terminal client deduplicates by run/sequence. `--event-log` appends all
observed transitions as JSONL across resets, including headless runs. Event
capture does not depend on reading a diagnostic snapshot. UART event times
identify the coupling boundary that observed the event,
while the original firmware text preserves any embedded mission clock.

Host coupling timing includes controller execution and physics, but excludes
viewer pacing, pauses and snapshot serialization. `compute_rtf` therefore
describes active computation throughput; it is not the overall mission RTF
in `race.speed_probe`, MCU latency or a physical driving-speed measurement.

For GDB, start the coupled simulation paused:

```powershell
.venv\Scripts\python.exe -m race --task 2 --backend renode --serve --serial-debug --monitor-stream --paused --gdb-port 3333
arm-none-eabi-gdb firmware/race/race_fw.elf
```

```gdb
target remote 127.0.0.1:3333
x/wx &law_seq
x/f &v_stop
x/f &w_cmd
detach
```

Pause before attaching; inspect without `continue` or `monitor start`, then
detach before `.venv\Scripts\python.exe -m race.monitor run`. Starting the
CPU alone would break the sensor/physics coupling. Renode's debugger halts virtual time when its CPU
halts ([Renode GDB documentation](https://renode.readthedocs.io/en/latest/debugging/gdb.html)).
The server is reattached to the fresh machine after reset. ARM/host `nm`
resolves the estimate symbols; set `ARM_NM`/`HOST_NM` if tool discovery fails.
The server starts with explicit `autostartEmulation=false`: the tested Renode
default otherwise starts emulation on attach and breaks the next coupled step.

Focused monitoring gates verify bounded histories, unchanged C duty outputs,
real symbol snapshots, 140 coupled serial cycles with no heartbeat gaps,
and actual GDB reads before and after cold reset, followed by successful
coupled resume after detach. A failed optional event-log write disables that
file sink and raises an event while control continues. SIM diagnostics still
require separate physical-board timing and current measurements.

[backend-monitoring-20261001.json](../firmware/evidence/backend-monitoring-20261001.json)
records the UI removal, default frame schema, terminal-client checks,
serial/GDB checks and the unchanged ELF hash. Earlier diagnostic-panel
screenshots in the speed-tuning evidence are historical.

## Backend performance profiling

Launch the native C backend at normal world speed with:

```powershell
.venv\Scripts\python.exe ops.py start race --task 4 --backend hostc
```

The launcher enables wall pacing for `hostc`. Both native C and Renode use
the same mission law; Renode additionally exercises the ARM firmware and
peripheral drivers. Use Renode for that contract and serial/GDB checks.
The launcher's default backend is the host-compiled C mission law. Use
`--backend stub` only for the Python reference controller, and use
`--no-turbo` only for an explicit slow/reference speed-table comparison on
tasks 1-3; task 4 remains the fast speed event.

Measure backend throughput without wall pacing or rendering:

```powershell
.venv\Scripts\python.exe -m race.perf_probe --backend hostc --seconds 1 --blocks 3 --warmup 1 --output output/native-performance.json
.venv\Scripts\python.exe -m race.perf_probe --backend renode --seconds 0.5 --blocks 3 --warmup 1 --output output/renode-performance.json
```

Add `--profile output/backend.prof` for a cProfile file. The JSON records
world/wall real-time factor (RTF), mean/p95 step time, process CPU time,
Windows resident/private memory, firmware heartbeat continuity and source/
artifact hashes. Stage timings come from a separate instrumented window;
inclusive categories overlap. Run one Renode probe at a time. Host RTF
measures computation throughput; world driving speed and MCU timing are
separate quantities.

The 2026-10-01 bounded measurements gave median RTF 11.06 for native C
and 0.160 for Renode. Renode's controller/peripheral path took 97.9% of
the instrumented window, including encoder-edge execution and the normal
firmware period. The paced native backend advanced 4.925 world seconds in
5.028 wall seconds, delivered 29.6 state messages/s and responded to
pause/run in about 31 ms. These are backend transport measurements.

Scheduling experiments gave no substantial benefit; two isolated C polling
variants were slower and were rejected. The production ELF, 5 ms control
period and tuned world-speed targets were preserved. Earlier measurements
on the same sources varied with host conditions, so this record makes no
Renode speedup claim. Five focused checks passed, including the native C
stress mission and duty/closed-loop parity. Full metrics and rejected
candidates are retained in
[runtime-performance-20261001.json](../firmware/evidence/runtime-performance-20261001.json).

## Historical state (2026-09-29, after the task-4 fix)

The measurements in this section describe the earlier profile, before the
line-array correction and the concurrent CAD/balance calibration update.
[line_status.md](../firmware/line_status.md) and `output/line-fidelity/` record
verification of the updated profile with source and ELF fingerprints.

**All four tasks grade PASS on the stub scorecard**: task 1 5.6 s/15,
stop 0.17 m; task 2 24.2 s/30, all nodes, stop 0.16 m; task 3 29.5 s/40,
all nodes, stop 0.15 m; task 4 121.2 s for 4 laps (16/16 nodes in order,
stop 0.06 m, worst node gt 0.18 m). The firmware e2e gates (Renode) hold
on the same constants: task-1 stub lockstep < 3 cm, tasks 2-4 grade PASS
through the peripheral path. Task 4 finishes in 121.593 s with 16/16 nodes
in order and a 0.061 m stop error; both encoder counters cross their
16-bit boundaries (2/6 crossings) and heartbeat matches all 24385
couplings. `firmware/enc_model.cs` replaces Renode 1.17's overflowing
encoder slice while preserving x4 edge injection and 16-bit CNT wrap;
[race_status.md](../firmware/race_status.md) and
[enc_status.md](../firmware/enc_status.md) own the simulation/board scope.

The task-4 opener (lap 4 lost, ~3 deg/lap of heading drift) was NOT gyro
error: the psi integral is honest (a probe measured 0.36 deg of estimate
error over a full arc). The drift came from the steering servo's ~8 Hz
rate relay: the 10 Hz yaw-rate lowpass lagged enough to sustain it, and
the relay's correlation with the tilt filter's lag leaked a DC term into
psi_dot = w/cos(theta). W_LPF_HZ 10 -> 16 halved the drift and task 4
completes with margin (the estimate still walks ~+7 deg over 4 laps --
the node resync plus the bar keep it from ever mattering). A geometric
psi anchor (body turning == path turning while the bar holds an arc) was
tried and REVERTED: on R40 the identity's path side needs arc-length
odometry whose scrub/lead error (~10% over a half-arc) swamps the 1-2
deg signal -- the anchor corrected the transient, not the drift
(output/t4_anchchk.log). Turbo headroom probed: straight legs pass at
0.30-0.34 m/s in that earlier simulation profile, with 0.35 its WIP cliff.
These measurements describe that snapshot rather than the current tuning
envelope.

## Known approximations

The line-array correction (2026-09-29) replaces point sampling with downward
optical projection, finite footprints and hysteresis. Python and C accept only
a contiguous detection as a line centroid, account for the forward bar in
odometry fusion, and keep one steering-error sign through loss and recovery.
The viewer now shows all eight channels with LEDs on over white and off over
black, separates raw array centering from heading and applied correction, and
draws the same tape geometry that the sensors read. Pause freezes both plant
and firmware. [line_status.md](../firmware/line_status.md) records the contract,
regression scenarios and optical assumptions.

- Wheel contact = sphere (bot convention): steering-scrub behavior differs
  from real tires; it is the root of the arc odometry drift and of half the
  troubleshooting bullets in this README.
- Sensor optical spot, thresholds, response and the 8-sensor 11 mm pitch are
  assumed. The listing gives a 91.11 mm envelope; backfill the shared profile
  after measuring the purchased array. Geometry-based detection does not yet
  predict ambient-light or reflectance effects.
- IMU has no noise/bias (bot convention); buzzer/LED are status bits, no
  acoustic model.
- The Python stub consumes RAC2 dataclass sensor frames. The peripheral
  firmware backend feeds IMU/ADC models, quadrature edges, and line-bar
  pins; RAC2 holds boot-time task configuration and firmware-owned telemetry.
- TIM3/TIM4 use the encoder slice in `firmware/enc_model.cs`, supporting
  the driver's unfiltered, noninverted x4 configuration only. Edge injectors
  drive the GPIO port receivers, so a wrong MODER/AF2 slice is rejected in sim;
  full alternate-function routing beyond these pins, RCC clock gating, and
  electrical behavior remain board checks. The PWM decoder gates on
  clock/CEN/CCxE/MOE/STBY; `TIM1Sim` stores BDTR for read-back, while PWM
  pin-waveform MOE gating and within-period phase are not modeled.
