"""Bounded backend throughput profiling. World/control clocks stay unchanged."""
import argparse
from collections import defaultdict
import cProfile
import ctypes
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

from bot.loop import COUPLING_S
from .loop import RaceLoop

ROOT = Path(__file__).resolve().parents[1]


def memory():
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [("size", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in
                ("peak_rss", "rss", "peak_paged", "paged", "peak_nonpaged",
                 "nonpaged", "pagefile", "peak_pagefile", "private")]
        data = Counters()
        data.size = ctypes.sizeof(data)
        get_handle = ctypes.windll.kernel32.GetCurrentProcess
        get_handle.restype = ctypes.c_void_p
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if get_info(get_handle(), ctypes.byref(data), data.size):
            return {name + "_mib": getattr(data, name) / 2**20
                    for name in ("rss", "peak_rss", "private")}
    return None


def probe(backend="hostc", task=2, seconds=1.0, blocks=3, warmup_s=1.0, profile_path=None):
    steps, warmup = round(seconds / COUPLING_S), round(warmup_s / COUPLING_S)
    if steps < 1 or blocks < 1 or warmup_s < 0:
        raise ValueError("seconds must cover a coupling, blocks must be positive, warmup nonnegative")
    if backend == "renode":
        from .renode_backend import RacePeriphBackend
        ctl = RacePeriphBackend(task=task)
        artifact = Path(ctl._elf_path)
    elif backend == "hostc":
        from .hostc_backend import RaceHostcController, DLL
        ctl = RaceHostcController(task=task)
        artifact = Path(DLL)
    else:
        raise ValueError("backend must be hostc or renode")
    try:
        loop = RaceLoop(task=task, controller=ctl)
        for _ in range(warmup):
            loop.step_coupling()
        rows = []
        for _ in range(blocks):
            seq, world = ctl.fw_seq, float(loop.data.time)
            latencies = []
            cpu, wall = time.process_time(), time.perf_counter()
            for _ in range(steps):
                start = time.perf_counter()
                loop.step_coupling()
                latencies.append(time.perf_counter() - start)
            wall, cpu = time.perf_counter() - wall, time.process_time() - cpu
            delta = float(loop.data.time) - world
            if ctl.fw_seq - seq != steps:
                raise RuntimeError("profiling lost a firmware cycle")
            ordered = sorted(latencies)
            rows.append({"steps": steps, "world_start_s": world, "world_delta_s": delta,
                         "wall_s": wall, "host_cpu_s": cpu, "cpu_core_equivalents": cpu / wall,
                         "rtf": delta / wall, "mean_step_ms": wall / steps * 1000,
                         "p95_step_ms": ordered[int(.95 * (steps - 1))] * 1000,
                         "heartbeat_delta": ctl.fw_seq - seq, "memory": memory()})
        # Instrument a separate window: the baseline above excludes this overhead.
        stages = defaultdict(lambda: [0, 0.0])
        restore = []
        def instrument(obj, method):
            fn = getattr(obj, method)
            def timed(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    stages[method][0] += 1
                    stages[method][1] += time.perf_counter() - start
            setattr(obj, method, timed)
            restore.append((obj, method, fn))
        for method in ("read_sensors", "apply_motors", "_observe_runtime"):
            instrument(loop, method)
        instrument(ctl, "step")
        if backend == "renode":
            for method in ("_write_bench", "_inject_encoder", "_drive_line"):
                instrument(ctl, method)
            for method in ("run", "run_period", "read_word", "write_word"):
                instrument(ctl._ch, method)
        profiler = cProfile.Profile() if profile_path else None
        if profiler:
            profiler.enable()
        started = time.perf_counter()
        try:
            for _ in range(steps):
                loop.step_coupling()
        finally:
            elapsed = time.perf_counter() - started
            if profiler:
                profiler.disable()
            for obj, method, fn in reversed(restore):
                setattr(obj, method, fn)
        if profiler:
            path = Path(profile_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            profiler.dump_stats(str(path))
        sources = ("race/perf_probe.py", "race/loop.py", "race/renode_backend.py",
                   "race/hostc_backend.py", "bot/renode.py", "firmware/race/race_law.c",
                   "firmware/race/race_fwconfig.h", "bot/mjcf.py", "bot/motors.py")
        return {"scope": "SIM host throughput, excludes startup/warmup, rendering and wall pacing; not physical MCU latency or driving speed.",
                "backend": backend, "task": task, "control_period_s": COUPLING_S,
                "warmup_world_s": warmup * COUPLING_S, "blocks": rows,
                "median_rtf": statistics.median(r["rtf"] for r in rows),
                "median_step_ms": statistics.median(r["mean_step_ms"] for r in rows),
                "stage_window": {"steps": steps, "wall_s": elapsed,
                                 "note": "Inclusive categories overlap; do not sum. This window includes instrumentation overhead.",
                                 "categories": {name: {"calls": values[0], "wall_s": values[1],
                                                        "wall_pct": values[1] / elapsed * 100}
                                                for name, values in stages.items()}},
                "heartbeat": ctl.fw_seq, "couplings": loop.monitor.steps,
                "heartbeat_gaps": loop.monitor.heartbeat_gaps,
                "artifact": {"path": str(artifact.resolve()), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
                "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}}
    finally:
        if backend == "renode":
            ctl._ch.emu.clear()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", choices=("hostc", "renode"), default="hostc")
    ap.add_argument("--task", type=int, choices=(1, 2, 3, 4), default=2)
    ap.add_argument("--seconds", type=float, default=1.0, help="world seconds per measurement block")
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--warmup", type=float, default=1.0, help="world seconds before measurement")
    ap.add_argument("--profile", help="save an optional cProfile file")
    ap.add_argument("--output", help="save JSON metrics")
    args = ap.parse_args(argv)
    report = probe(args.backend, args.task, args.seconds, args.blocks, args.warmup, args.profile)
    raw = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw + "\n", encoding="utf-8")
    print(raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
