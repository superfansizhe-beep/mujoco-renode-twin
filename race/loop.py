"""Race loop: BotLoop on the exam field.

BotLoop (bot/loop.py) carries the whole coupling discipline -- 200 Hz
sensor->mailbox->controller->zero-order-held torque->5 x 1 ms physics,
state frames via bot.telemetry, the run() driver. This subclass swaps
in the race WORLD (bot mjcf verbatim, the line-bar sites native, a
spawn per task) and the mission controller, and stamps fresh controller
node events with ground truth for the grader. The car runs bar-first:
travel = chassis -Y (race/spawn.py), hence travel_y=-1 in state().

Ground truth lives HERE only: state() broadcasts it for the grader;
the controller never sees it.
"""
import math
import time
import json
from pathlib import Path

import mujoco

from bot import motors, telemetry
from bot.loop import COUPLING_S, BotLoop
from bot.mjcf import line_site_ids
from bot.line_sensor import LineArray, observe

from . import mailbox, track, tasks
from .controller import RaceController
from .spawn import spawn_for_task


class RaceLoop(BotLoop):
    MOTOR_FRAME = mailbox.RaceMotorFrame

    def __init__(self, task: int = 2, battery: str = "3s",
                 turbo: bool | None = None, controller=None, event_log=None,
                 monitor_stream: bool = False) -> None:
        # the controller slot: the Python stub by default, or a caller-
        # injected controller (RacePeriphBackend, --backend renode) --
        # the bot Controller discipline, same interface either way
        slot = controller if controller is not None else RaceController(
            task, COUPLING_S, motors.BATTERY_NOMINAL[battery], turbo=turbo)
        self._line_array = LineArray()
        self._line_sample = None
        self._line_sample_seq = None
        self._event_log = event_log
        self._monitor_stream = monitor_stream
        super().__init__(battery=battery, controller=slot)
        # the race world's own plumbing (base reset already ran in super)
        self._line_sites = line_site_ids(self.model)

    def reset(self, task: int | None = None) -> None:
        if task is not None and task != self.controller.task:
            if hasattr(self.controller, "retask"):
                # firmware backend: new task word -> machine cold boot
                self.controller.retask(task)
            else:
                self.controller = RaceController(
                    task, COUPLING_S, self.v_batt,
                    turbo=self.controller.turbo)
        mujoco.mj_resetData(self.model, self.data)
        qpos, spawn = spawn_for_task(self.model, self.controller.task)
        self.data.qpos[:] = qpos
        mujoco.mj_forward(self.model, self.data)
        self._seq = 0
        self._enc_l.reset()
        self._enc_r.reset()
        self._acc_lpf.reset()
        self._line_array.reset()
        self._line_sample = None
        self._line_sample_seq = None
        self.controller.reset(spawn["x"], spawn["y"], spawn["psi"])
        self.spawn = spawn
        self._ev_len = 0
        self.paused = False
        self.last_sensor = None
        self.last_motor = self.MOTOR_FRAME()
        from .monitoring import RaceMonitor
        self.monitor = RaceMonitor(self._event_log)
        self.monitor.emit("simulation.reset", self.data.time, 0,
                          task=self.controller.task, backend=self.controller.name)

    def set_task(self, task: int, turbo: bool | None = None) -> None:
        if hasattr(self.controller, "retask"):
            # firmware: task/turbo live in the task word; changing either
            # is a cold boot (the stub rebuilds itself the same way)
            self.controller.retask(task, turbo=turbo)
            self.reset()
            return
        if turbo is not None:
            self.controller.turbo = turbo
        self.reset(task)

    # ---------------- sensor path (harness -> mailbox) ----------------
    def read_sensors(self) -> mailbox.RaceSensorFrame:
        d = self.data
        self._line_sample = self._line_array.sample(
            d.site_xpos[self._line_sites], d.site_xmat[self._line_sites],
            track.over_tape)
        self._line_sample_seq = self._seq
        return mailbox.RaceSensorFrame(seq=self._seq,
                                       line_bits=self._line_sample.black_bits,
                                       **self._imu_enc_fields())

    def _annotate(self, motor) -> None:
        """Ground-truth distance on fresh controller node events (grader
        input; the controller itself never sees these numbers)."""
        evs = self.controller.events
        fresh = evs[self._ev_len:]
        for ev in fresh:
            node = track.NODES.get(ev.get("node", ""))
            if node is not None:
                ev["gt_dist"] = round(math.hypot(
                    self.data.qpos[0] - node[0],
                    self.data.qpos[1] - node[1]), 3)
        self._ev_len = len(evs)
        mission = self.controller.info()
        route = tasks.task_route(self.controller.task)
        seg = route[min(mission["seg_i"], len(route) - 1)]
        self.monitor.observe(self.data.time, motor, mission, seg.taped,
                             COUPLING_S, fresh)

    def step_coupling(self):
        if self.paused:
            self._observe_runtime()
            return super().step_coupling()
        world_before = self.data.time
        started = time.perf_counter()
        try:
            return super().step_coupling()
        except Exception as exc:
            self.monitor.emit("control.fault", self.data.time,
                              self.last_motor.fw_seq, "error", message=str(exc))
            raise
        finally:
            self.monitor.timing(time.perf_counter() - started,
                                self.data.time - world_before)
            self._observe_runtime()

    def _observe_runtime(self):
        serial_method = getattr(self.controller, "serial_diagnostics", None)
        serial = serial_method() if serial_method else None
        self.monitor.observe_runtime(self.data.time, self.last_motor.fw_seq,
                                     self.paused, abs(self.tilt_deg()) > 45.0, serial)
        return serial

    # ---------------- telemetry (ground truth included) ----------------
    def gt(self) -> dict:
        """Ground-truth travel pose: axle position, heading of the travel
        direction (chassis -Y), speed along it."""
        d = self.data
        w, x, y, z = d.qpos[3:7]
        yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
        yb = (-math.sin(yaw), math.cos(yaw))            # chassis +Y, world
        v_travel = -(d.qvel[0] * yb[0] + d.qvel[1] * yb[1])
        psi = (yaw - math.pi / 2 + math.pi) % (2 * math.pi) - math.pi
        return {"x": round(d.qpos[0], 4), "y": round(d.qpos[1], 4),
                "psi": round(psi, 4), "v": round(v_travel, 4)}

    def state(self, *, include_debug: bool | None = None) -> dict:
        m = getattr(self, "last_motor", self.MOTOR_FRAME())
        st = telemetry.pose_fields(
            self.data,
            duty=[m.duty_l, m.duty_r],
            enc=[self._enc_l.counts, self._enc_r.counts],
            batt_v=self.v_batt,
            paused=self.paused,
            travel_y=-1.0,   # bar-first: travel = chassis -Y (spawn.py)
            fw_seq=m.fw_seq)   # stub: fw-shaped seq; firmware: heartbeat
        st["mission"] = self.controller.info()
        sample = self._line_sample
        if sample is None:
            # Initial view only: no encoder update or controller cycle here.
            sample = self._line_array.sample(
                self.data.site_xpos[self._line_sites],
                self.data.site_xmat[self._line_sites], track.over_tape)
        st["line"] = sample.payload()
        st["line"]["seq"] = self._line_sample_seq
        consumed = st["mission"].get("line_bits")
        st["line"]["consumed_bits"] = consumed
        st["line"]["observation"] = observe(
            sample.black_bits if consumed is None else consumed).payload()
        st["line"]["matches"] = consumed is None or consumed == sample.black_bits
        route = tasks.task_route(self.controller.task)
        seg = route[min(st["mission"]["seg_i"], len(route) - 1)]
        st["line"]["expected_tape"] = seg.taped
        serial = self._observe_runtime()
        if not (self._monitor_stream if include_debug is None else include_debug):
            return st
        started = time.perf_counter()
        diagnostics = getattr(self.controller, "diagnostics", None)
        estimates = diagnostics() if diagnostics else {
            "available": False, "reason": "backend has no estimate snapshot"}
        st["debug"] = self.monitor.snapshot(st["t"], m.fw_seq, self.paused,
                                             st["fallen"], serial)
        st["debug"]["estimates"] = estimates
        st["debug"]["serial"] = serial
        st["debug"]["host"]["diagnostic_read_ms"] = 1000 * (time.perf_counter() - started)
        return st

    # ---------------- drivers ----------------
    def save_snapshot(self, directory=None) -> str:
        """Save an observed state locally, without a control or physics step."""
        folder = Path(directory) if directory else Path(__file__).resolve().parents[1] / "output/race-debug"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"race-debug-{self.monitor.run_id[:8]}-{time.time_ns()}.json"
        snapshot = self.state(include_debug=True)
        snapshot_path = str(path.resolve())
        snapshot["debug"]["saved_snapshot"] = snapshot_path
        if self.controller.phase == "done":
            snapshot["grade"] = grade(self)
        path.write_text(json.dumps(snapshot, indent=2, allow_nan=False), encoding="utf-8")
        self.monitor.saved_snapshot = snapshot_path
        self.monitor.emit("snapshot.saved", self.data.time, self.last_motor.fw_seq,
                          path=self.monitor.saved_snapshot)
        return self.monitor.saved_snapshot

    def run_until_done(self, timeout_s: float, realtime: bool = False,
                       on_state=None, progress_hz: float = 0.0,
                       on_command=None) -> dict:
        """Run until the mission is done (or timeout); returns the
        grader verdict. on_command() fires at every coupling boundary
        so the server can inject task switches / resets / pauses
        mid-chunk (bot.loop.run's on_step)."""
        mark = 0.0
        while self.data.time < timeout_s:
            # state_hz above the wire's 30 Hz: the firmware backend's
            # steps run ~27 ms wall (slower than realtime), and a lower
            # push gate skips steps -- the viewer then sees half the
            # wire rate
            self.run(0.1, realtime=realtime, on_state=on_state,
                     state_hz=60.0, on_step=on_command)
            if self.controller.phase == "done":
                break
            if progress_hz and self.data.time - mark >= 1.0 / progress_hz:
                mark = self.data.time
                st = self.state()
                print(f"t={st['t']:6.2f} seg={st['mission']['seg']:>4s} "
                      f"lap={st['mission']['lap']}/{st['mission']['laps']} "
                      f"v={st['speed_mps']:+.3f} "
                      f"e={st['mission']['e_lat_mm']:+5.1f}mm "
                      f"odo=({st['mission']['odo'][0]:.2f},"
                      f"{st['mission']['odo'][1]:.2f}) "
                      f"pos=({st['pos'][0]:.2f},{st['pos'][1]:.2f})")
        return grade(self)


# ---------------- ground-truth grader ----------------
def grade(loop: RaceLoop) -> dict:
    """Score a finished (or timed-out) run against the exam sheet using
    MuJoCo ground truth: beep placement (GT distance recorded by the
    loop at each node event), stop quality, total time vs the limit."""
    ctl = loop.controller
    spec = ctl.spec
    ends = [track.node_at(*o.point(o.length), tol=0.02)
            for o in spec["route"]]
    node_events = [e for e in ctl.events if e["kind"] == "node"]
    # beep placement: our own scoring choice -- every beep fires within
    # 0.30 m of its node, the car-length "node zone" (the sheet
    # quantifies neither radius nor tolerance, only "a beep at each
    # node"; the finish line is dead-reckoned ~0.3 m early BY DESIGN so
    # the brake lands the stop in the zone)
    beep_seq_ok = ([e["node"] for e in node_events] == ends
                   and all(e.get("gt_dist", 1.0) <= 0.30 for e in node_events))
    gt_pos = (loop.data.qpos[0], loop.data.qpos[1])
    final_node = track.NODES[ends[-1]]   # the route's last end IS the stop
    stop_dist = math.hypot(gt_pos[0] - final_node[0], gt_pos[1] - final_node[1])
    elapsed = ctl.info()["elapsed"]
    verdict = {
        "task": spec["task"],
        "done": ctl.phase == "done",
        "elapsed_s": elapsed,
        "limit_s": spec["limit_s"],
        "within_limit": (elapsed is not None
                         and (spec["limit_s"] is None
                              or elapsed <= spec["limit_s"])),
        "nodes": [e["node"] for e in node_events],
        "beep_seq_ok": beep_seq_ok,
        "stop_dist_m": round(stop_dist, 3),
        "stop_ok": ctl.phase == "done" and stop_dist <= 0.30,
        "fallen": bool(abs(loop.tilt_deg()) > 45.0),
    }
    verdict["pass"] = (verdict["done"] and verdict["within_limit"]
                       and verdict["beep_seq_ok"] and verdict["stop_ok"]
                       and not verdict["fallen"])
    return verdict
