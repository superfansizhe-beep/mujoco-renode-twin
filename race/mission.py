"""RaceMissionCore -- the channel-free mission surface every race
controller slot shares (the Renode mailbox backend, the Renode
peripheral backend, the host-DLL law).

Route helpers, the task word, turbo semantics, event synthesis from
buzzer edges and the stub's info() shape live HERE once. Backends own
only their channel -- a Renode machine or a host DLL -- and how one
cycle's observable outputs arrive; the loop, the viewer and the grader
cannot tell the slots apart except by name and speed."""
from . import tasks, track
from .controller import ARM_S, BEEP_MS
from .mailbox import RaceMotorFrame

PHASES = ("arm", "run", "brake", "done")


class RaceMissionCore:
    """The controller surface's mission half (task/turbo/phase/events/
    info); the channel half (step/reset plumbing) stays with each
    backend."""

    def __init__(self, task: int, dt: float,
                 turbo: bool | None = None) -> None:
        self.task = task
        # Fast mode is the normal exam profile for every task. Keep an
        # explicit False as a deliberate safe/reference override so the
        # slow table remains available for controlled comparisons.
        self.turbo = (True if turbo is None else bool(turbo)) or task == 4
        self.dt = dt
        self.fw_seq = 0
        self.phase = "arm"
        self.events: list[dict] = []
        self._prev_buzzer = 0
        self._edge_i = 0
        self._ends = self._route_ends(task)
        self._t_sim = 0.0
        self._last_m = RaceMotorFrame()
        self._consumed_line_bits = None

    def _reset_mission(self) -> None:
        """Fresh-mission state; the channel reset is the backend's own."""
        self.fw_seq = 0
        self.phase = "arm"
        self.events = []
        self._prev_buzzer = 0
        self._edge_i = 0
        self._t_sim = 0.0
        self._last_m = RaceMotorFrame()
        self._consumed_line_bits = None

    # ---------------- route helpers (Python-side, same source) ----------------
    @staticmethod
    def _route_ends(task: int) -> list:
        return [track.node_at(*o.point(o.length), tol=0.02)
                for o in tasks.task_route(task)]

    @property
    def spec(self) -> dict:
        """grade() reads spec/route/laps/limit -- the Python track is the
        same single source the header was generated from."""
        return tasks.task_spec(self.task)

    def retask(self, task: int, turbo: bool | None = None) -> None:
        """Task switch = new task word = fresh mission (the stub rebuilds
        itself the same way; omitted turbo keeps the fast exam profile)."""
        self.task = task
        if turbo is not None:
            self.turbo = bool(turbo)
        self.turbo = self.turbo or task == 4
        self._ends = self._route_ends(task)
        self.reset()

    def _task_word(self) -> int:
        return (self.task & 0xFF) | (0x100 if self.turbo else 0)

    # ---------------- observable-mission adapter ----------------
    def _absorb_outputs(self, m: RaceMotorFrame) -> None:
        """Post-cycle bookkeeping every slot shares once its channel has
        produced the observable outputs."""
        self.fw_seq = m.fw_seq
        self._t_sim += self.dt
        self._last_m = m
        self.phase = PHASES[m.status & 0xFF]
        self._synthesize_events(m)

    def _synthesize_events(self, m: RaceMotorFrame) -> None:
        """Node beeps = buzzer rising edges, named by route order (the
        firmware beeps each segment end in order -- by construction).
        The arrival chirp is 3x the node beep -- but the carried value
        is post-countdown (150-5 / 450-5, the law counts down before
        the mirror, same as the stub's return), so the discriminator is
        2xBEEP_MS, well above 145 and below 445."""
        if self._prev_buzzer == 0 and m.buzzer_ms > 0:
            if m.buzzer_ms >= 2 * BEEP_MS:
                self.events.append({"kind": "done", "node": "A",
                                    "t": round(self._t_sim, 3)})
            elif self._edge_i == 0 and self.task != 1:
                self.events.append({"kind": "start", "node": "A",
                                    "t": round(self._t_sim, 3)})
                self._edge_i = 1
            else:
                idx = self._edge_i - (1 if self.task != 1 else 0)
                node = self._ends[idx] if idx < len(self._ends) else "?"
                self.events.append({"kind": "node", "node": node,
                                    "t": round(self._t_sim, 3)})
                self._edge_i += 1
        self._prev_buzzer = m.buzzer_ms

    def info(self) -> dict:
        """The stub's info() shape, filled from the last cycle's
        observable outputs."""
        route = tasks.task_route(self.task)
        n = len(route)
        seg_i = min((self._last_m.status >> 8) & 0xFF, n - 1)
        laps = self.spec["laps"]
        per_lap = n // laps
        t_ms = self._last_m.t_mission_ms
        elapsed = round(t_ms / 1000.0, 3) if self.phase != "arm" else None
        t_start = ARM_S if self.phase != "arm" else None
        t_done = round(ARM_S + t_ms / 1000.0, 3) \
            if self.phase == "done" else None
        return {
            "task": self.task,
            "phase": self.phase,
            "seg": route[seg_i].name,
            "seg_i": seg_i,
            "lap": min(seg_i // per_lap + 1, laps),
            "laps": laps,
            "v_plan": round(self._last_m.v_plan_mm_s / 1000.0, 3),
            "odo": [round(self._last_m.odo_cm[0] / 100.0, 4),
                    round(self._last_m.odo_cm[1] / 100.0, 4)],
            "psi": None,               # not exported by the backends (HUD-only)
            "e_lat_mm": float(self._last_m.e_lat_mm),
            "line_bits": getattr(self, "_consumed_line_bits", None),
            "line_source": {0: "odometry", 1: "sensor", 2: "hold"}.get(
                (self._last_m.status >> 16) & 3, "unknown"),
            "w_meas": None,
            "w_cmd": None,
            "buzzer": self._last_m.buzzer_ms > 0,
            "led": self._last_m.led > 0,
            "events": list(self.events),
            "t_start": t_start,
            "t_done": t_done,
            "elapsed": elapsed,
        }
