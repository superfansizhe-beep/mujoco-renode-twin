"""Bounded observation history. It never participates in control decisions."""
from collections import deque
import json
from pathlib import Path
import uuid

from .controller import LOST_S, SWEEP_AFTER, BalanceController


class RaceMonitor:
    def __init__(self, event_log=None, capacity=64):
        self.run_id = uuid.uuid4().hex
        self.events = deque(maxlen=capacity)
        self.seq = 0
        self.event_log = Path(event_log) if event_log else None
        if self.event_log:
            self.event_log.parent.mkdir(parents=True, exist_ok=True)
        self._phase_segment = None
        self._lost_s = self._rail_s = 0.0
        self._recovery = 0
        self._saturated = False
        self._last_heartbeat = 0
        self._serial_seq = 0
        self._paused = False
        self._fallen = False
        self.heartbeat_gaps = 0
        self.steps = 0
        self.saved_snapshot = None
        self._timings = deque(maxlen=200)
        self._world_advanced = 0.0
        self._compute_s = 0.0

    def emit(self, kind, world_s, fw_seq, severity="info", source="sim_monitor", **details):
        self.seq += 1
        event = {"seq": self.seq, "run_id": self.run_id, "kind": kind,
                 "world_s": round(world_s, 6), "fw_seq": fw_seq,
                 "severity": severity, "source": source, "details": details}
        self.events.append(event)
        if self.event_log:
            try:
                with self.event_log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, allow_nan=False) + "\n")
            except OSError as exc:
                self.event_log = None  # a disk failure must not stop the controller
                self.emit("monitor.log_error", world_s, fw_seq, "warning", message=str(exc))

    def observe(self, world_s, motor, mission, expected_tape, dt, fresh_events):
        fw_seq = motor.fw_seq
        phase_segment = (mission["phase"], mission["seg_i"])
        if phase_segment != self._phase_segment:
            self.emit("mission.phase_segment", world_s, fw_seq,
                      phase=mission["phase"], segment=mission["seg"],
                      seg_i=mission["seg_i"], lap=mission["lap"])
            self._phase_segment = phase_segment
            self._lost_s = 0.0
        for event in fresh_events:
            self.emit("mission." + event["kind"], world_s, fw_seq, event=dict(event))
        gap = fw_seq - self._last_heartbeat - 1
        if gap != 0:
            self.heartbeat_gaps += abs(gap)
            self.emit("control.heartbeat_gap", world_s, fw_seq, "warning", delta=gap)
        self._last_heartbeat = fw_seq
        # Darkness on the untaped legs is planned. These events describe
        # sustained missing observations, while the C lost_t remains an estimate.
        lost = expected_tape and mission["phase"] == "run" and mission["line_source"] != "sensor"
        self._lost_s = self._lost_s + dt if lost else 0.0
        recovery = 2 if self._lost_s >= SWEEP_AFTER else 1 if self._lost_s >= LOST_S else 0
        if recovery != self._recovery:
            if recovery:
                self.emit("line.recovery_observed", world_s, fw_seq, "warning",
                          stage="search" if recovery == 2 else "slowdown",
                          unobserved_s=round(self._lost_s, 3))
            elif self._recovery:
                self.emit("line.recovery_ended", world_s, fw_seq,
                          reason="sensor" if mission["line_source"] == "sensor" else "route_or_phase")
            self._recovery = recovery
        rail = max(abs(motor.duty_l), abs(motor.duty_r)) >= BalanceController.DUTY_CAP
        self._rail_s = self._rail_s + dt if rail else 0.0
        saturated = self._rail_s >= 0.1
        if saturated and not self._saturated:
            self.emit("control.saturation", world_s, fw_seq, "warning",
                      duration_s=round(self._rail_s, 3), duty=[motor.duty_l, motor.duty_r])
        elif not rail and self._saturated:
            self.emit("control.saturation_ended", world_s, fw_seq)
        self._saturated = saturated

    def timing(self, seconds, world_delta):
        self.steps += 1
        self._timings.append(seconds)
        self._compute_s += seconds
        self._world_advanced += world_delta

    def observe_runtime(self, world_s, fw_seq, paused, fallen, serial=None):
        """Record runtime transitions independently of diagnostic consumers."""
        if paused != self._paused:
            self.emit("simulation.paused" if paused else "simulation.resumed", world_s, fw_seq)
            self._paused = paused
        if fallen != self._fallen:
            self.emit("simulation.fallen" if fallen else "simulation.upright", world_s, fw_seq,
                      "warning" if fallen else "info")
            self._fallen = fallen
        if serial:
            for event in serial["events"]:
                if event["seq"] > self._serial_seq:
                    self.emit("serial.rx", world_s, fw_seq, text=event["text"],
                              serial_seq=event["seq"], command=event.get("command"),
                              source="firmware_uart")
                    self._serial_seq = event["seq"]

    def snapshot(self, world_s, fw_seq, paused, fallen, serial=None):
        self.observe_runtime(world_s, fw_seq, paused, fallen, serial)
        times = sorted(self._timings)
        return {"schema": 1, "run_id": self.run_id,
                "events": list(self.events), "last_seq": self.seq,
                "first_seq": self.events[0]["seq"] if self.events else 0,
                "dropped_events": max(0, self.seq - len(self.events)),
                "heartbeat_gaps": self.heartbeat_gaps,
                "saved_snapshot": self.saved_snapshot,
                "host": {"couplings": self.steps,
                         "step_last_ms": 1000 * self._timings[-1] if times else None,
                         "step_mean_ms": 1000 * sum(times) / len(times) if times else None,
                         "step_p95_ms": 1000 * times[int(.95 * (len(times) - 1))] if times else None,
                         "compute_rtf": self._world_advanced / self._compute_s if self._compute_s else None,
                         "scope": "Active coupling computation only; excludes pause, viewer pacing and state serialization. World driving speed uses simulation time."}}
