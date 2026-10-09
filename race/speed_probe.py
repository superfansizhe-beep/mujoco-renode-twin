"""Measure driving speed in plant time, independently of host throughput.

Example: python -m race.speed_probe --backend renode --task 4 --stress
         --output output/speed-probe.json
Build firmware/race/race_fw.elf first. Renode retains the production
peripheral path and its default emulated CPU rate; this probe never speeds
the physics clock or supplies ground truth to the controller.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import time

import mujoco
import numpy as np

from bot.backend import BalanceController
from bot.loop import COUPLING_S
from . import tasks
from .controller import STOP_S
from .loop import RaceLoop, grade
from .mailbox import RaceMotorFrame

ROOT = Path(__file__).resolve().parents[1]


def probe(task=4, backend="hostc", battery_v=11.1, friction=None,
          actuator_delay=False, nudge_at=None, cap_s=150.0, elf_path=None,
          progress=None):
    if cap_s <= 0.0:
        raise ValueError("cap_s must be positive")
    if backend == "renode":
        from .renode_backend import RacePeriphBackend
        ctl = RacePeriphBackend(task=task, elf_path=elf_path)
        artifact = Path(ctl._elf_path)
    elif backend == "hostc":
        from .hostc_backend import RaceHostcController, DLL
        ctl = RaceHostcController(task=task)
        artifact = Path(DLL)
    else:
        raise ValueError(f"Unknown backend: {backend}")
    loop = RaceLoop(task=task, controller=ctl)
    loop.v_batt = battery_v
    if friction is not None:
        floor = mujoco.mj_name2id(loop.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        if floor < 0:
            raise RuntimeError("floor geom missing")
        loop.model.geom_friction[floor, 0] = friction
    if actuator_delay:
        apply = loop.apply_motors
        pending = [RaceMotorFrame()]

        def delayed(motor):
            apply(pending[0])
            pending[0] = motor

        loop.apply_motors = delayed

    groups = {k: {"v": [], "rail": 0} for k in ("straight", "arc")}
    recent = deque(maxlen=round(STOP_S / COUPLING_S))
    route = tasks.task_route(task)
    wraps = [0, 0]
    if backend == "renode":
        from bot.periph import TIM3_CNT, TIM4_CNT
        counter_addrs = (TIM3_CNT, TIM4_CNT)
        last_raw = [ctl._ch.read_word(a) & 0xFFFF for a in counter_addrs]
    previous_seq = steps = gaps = 0
    max_tilt = distance = 0.0
    start_world = None
    next_report = 10.0
    pushed = False
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        while loop.data.time < cap_s and ctl.phase != "done":
            info = ctl.info()
            active = ctl.phase == "run"
            seg = route[min(info["seg_i"], len(route) - 1)]
            xy_before = loop.data.qpos[:2].copy()
            if nudge_at is not None and not pushed and loop.data.time >= nudge_at:
                loop.nudge(fx=6.0, tx=0.03)
                pushed = True
            loop.step_coupling()
            steps += 1
            gaps += int(ctl.fw_seq != previous_seq + 1)
            previous_seq = ctl.fw_seq
            if backend == "renode":
                raw = [ctl._ch.read_word(a) & 0xFFFF for a in counter_addrs]
                for wheel in range(2):
                    wraps[wheel] += int(abs(raw[wheel] - last_raw[wheel]) > 0x8000)
                last_raw = raw
            distance += float(np.linalg.norm(loop.data.qpos[:2] - xy_before))
            gt = loop.gt()
            recent.append((gt["v"], gt["x"], gt["y"]))
            max_tilt = max(max_tilt, abs(loop.tilt_deg()))
            if start_world is None and ctl.phase != "arm":
                start_world = float(loop.data.time - COUPLING_S)
            if active:
                g = groups["arc" if seg.taped else "straight"]
                g["v"].append(gt["v"])
                g["rail"] += int(max(abs(loop.last_motor.duty_l),
                                     abs(loop.last_motor.duty_r))
                                 >= BalanceController.DUTY_CAP)
            if progress is not None and loop.data.time >= next_report:
                progress({"world_s": round(float(loop.data.time), 3),
                          "wall_s": round(time.perf_counter() - wall_start, 2),
                          "seg_i": ctl.info()["seg_i"], "heartbeat": ctl.fw_seq})
                next_report += 10.0
            if max_tilt > 45.0:
                break
        wall_s = time.perf_counter() - wall_start
        cpu_s = time.process_time() - cpu_start
        world_s = float(loop.data.time)
        mission_s = world_s - start_world if start_world is not None else None
        verdict = grade(loop)
        speed_stats = {}
        for kind, g in groups.items():
            if g["v"]:
                speed_stats[kind] = {
                    "sampled_world_s": len(g["v"]) * COUPLING_S,
                    "mean_mps": float(np.mean(g["v"])),
                    "median_mps": float(np.median(g["v"])),
                    "p95_mps": float(np.percentile(g["v"], 95)),
                    "peak_mps": float(max(g["v"])),
                    "duty_rail_percent": 100.0 * g["rail"] / len(g["v"]),
                }
        samples = np.array(recent)
        files = [artifact, ROOT / "firmware/race/race_law.c",
                 ROOT / "firmware/race/race_fwconfig.h",
                 ROOT / "firmware/twin/twin_fwconfig.h",
                 ROOT / "race/speed_probe.py", ROOT / "bot/motors.py",
                 ROOT / "bot/mjcf.py", ROOT / "bot/loop.py",
                 ROOT / "race/renode_backend.py"]
        hashes = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in files}
        return {
            "scope": "SIM; real motor current, battery sag, sensor bias and physical-board timing remain unmeasured",
            "timing": "Driving speed uses MuJoCo world time. Host latency affects wall_s/rtf only. MCU and actuator latency remain in the loop.",
            "backend": backend, "task": task, "battery_v": battery_v,
            "floor_friction_override": friction,
            "extra_actuator_delay_s": COUPLING_S if actuator_delay else 0.0,
            "nudge_at_world_s": nudge_at, "verdict": verdict,
            "world_total_s": world_s, "world_mission_s": mission_s,
            "wall_s": wall_s, "host_cpu_s": cpu_s, "rtf": world_s / wall_s,
            "world_path_m": distance, "path_average_mps": distance / world_s,
            "route_progress_mps": (tasks.route_length(task) / mission_s
                                   if verdict["pass"] else None),
            "max_tilt_deg": max_tilt, "couplings": steps,
            "heartbeat": ctl.fw_seq, "heartbeat_gaps": gaps,
            "encoder_wraps": wraps if backend == "renode" else None,
            "stop_hold_body_speed_peak_mps": float(np.abs(samples[:, 0]).max()),
            "stop_hold_xy_span_m": np.ptp(samples[:, 1:], axis=0).tolist(),
            "speed_statistics": speed_stats, "sha256": hashes,
        }
    finally:
        if backend == "renode":
            ctl._ch.emu.clear()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", choices=("hostc", "renode"), default="hostc")
    ap.add_argument("--task", type=int, choices=(1, 2, 3, 4), default=4)
    ap.add_argument("--stress", action="store_true",
                    help="10.5 V, friction 1.0, a shove at 10 s and one extra 5 ms actuator hold")
    ap.add_argument("--battery-v", type=float)
    ap.add_argument("--cap-s", type=float, default=150.0)
    ap.add_argument("--elf", help="Built ARM ELF for the Renode backend")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    kwargs = ({"friction": 1.0, "actuator_delay": True, "nudge_at": 10.0}
              if args.stress else {})
    result = probe(task=args.task, backend=args.backend,
                   battery_v=args.battery_v if args.battery_v is not None
                   else (10.5 if args.stress else 11.1),
                   cap_s=args.cap_s, elf_path=args.elf,
                   progress=lambda row: print(json.dumps(row), flush=True), **kwargs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"]["pass"] and result["heartbeat_gaps"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
