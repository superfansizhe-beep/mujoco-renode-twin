"""Race CLI.

  python -m race --task 2 --realtime --serve    # C-driven fast viewer
  python -m race --task 1                       # C-driven fast, graded
  python -m race --all                          # C-driven fast tasks 1-4
  python -m race --task 2 --backend hostc       # C mission law on the host (fast)
  python -m race --task 2 --backend renode      # REAL C firmware (Renode)

Headless runs stop as soon as the mission completes (or --timeout),
then print the ground-truth grader verdict. --serve streams state on
:8766 for the shared 3D viewer (web/, `?ws=ws://127.0.0.1:8766`),
opening each connection with a scene frame that embeds the track
(race/scene.py), and
stays alive after each mission -- switch tasks from the viewer, Ctrl+C
to exit. Fast mode is the default for all four tasks; `--no-turbo` is a
deliberate slow/reference override for tasks 1-3, while task 4 remains the
speed event. The default controller is the
host-compiled C mission law; `--backend renode` swaps in
firmware/race/race_fw.elf for the real peripheral path (needs the [renode]
extra + a built ELF; constants come from race.fwconfig).
"""
import argparse
import json
import sys
import time

from bot import motors
from bot.loop import COUPLING_S

from . import tasks
from .loop import RaceLoop

TIMEOUTS = {1: 30.0, 2: 60.0, 3: 60.0, 4: 150.0}


def _hostc_backend(args, task: int):
    from .hostc_backend import RaceHostcController
    return RaceHostcController(
        task=task, dt=COUPLING_S,
        v_batt=motors.BATTERY_NOMINAL[args.battery],
        turbo=args.turbo)


def _firmware_backend(args, task: int):
    from .renode_backend import RacePeriphBackend
    debug = {}
    if getattr(args, "serial_debug", False):
        debug["uart_telemetry"] = True
    if getattr(args, "gdb_port", None) is not None:
        debug["gdb_port"] = args.gdb_port
    return RacePeriphBackend(
        task=task,
        dt=COUPLING_S,
        v_batt=motors.BATTERY_NOMINAL[args.battery],
        turbo=args.turbo, **debug)


def run_task(task: int, turbo=None, timeout=None, verbose=False,
             backend=None, event_log=None, battery="3s") -> dict:
    loop = RaceLoop(task=task, battery=battery, turbo=turbo,
                    controller=backend, event_log=event_log)
    return loop.run_until_done(timeout or TIMEOUTS[task],
                               progress_hz=1.0 if verbose else 0.0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="race")
    ap.add_argument("--task", type=int, choices=tuple(tasks.TASKS),
                    default=2)
    ap.add_argument("--all", action="store_true",
                    help="run tasks 1-4 headless and print a verdict table")
    ap.add_argument("--turbo", action="store_true", default=None,
                    help="fast speed table (already the default for tasks 1-4)")
    ap.add_argument("--no-turbo", dest="turbo", action="store_false",
                    help="slow/reference table for tasks 1-3; task 4 stays fast")
    ap.add_argument("--battery", choices=sorted(motors.BATTERY_NOMINAL),
                    default="3s")
    ap.add_argument("--timeout", type=float, default=None,
                    help="virtual-second cap per task")
    ap.add_argument("--serve", action="store_true",
                    help="websocket state stream on :8766 for the 3D twin "
                         "viewer (web/?ws=ws://127.0.0.1:8766)")
    ap.add_argument("--backend", choices=("stub", "hostc", "renode"),
                    default="hostc",
                    help="controller slot: host-compiled C mission law (default), "
                    "Python reference stub, or the real C "
                         "firmware in Renode (I2C/GPIO/encoder/PWM; "
                         "needs [renode] extra + race_fw.elf)")
    ap.add_argument("--realtime", action="store_true",
                    help="pace to wall clock (for viewing)")
    ap.add_argument("--port", type=int, default=8766,
                    help="websocket port for --serve (ops.py routes "
                         "isolated gates through this)")
    ap.add_argument("--verbose", action="store_true",
                    help="1 Hz progress lines in headless runs")
    ap.add_argument("--serial-debug", action="store_true",
                    help="capture existing USART2 output and enable paced ping/stat (Renode)")
    ap.add_argument("--gdb-port", type=int,
                    help="start Renode GDB server; requires --serve --paused")
    ap.add_argument("--paused", action="store_true",
                    help="start the viewer with both plant and controller paused")
    ap.add_argument("--event-log", help="append diagnostic transitions as JSON lines")
    ap.add_argument("--monitor-stream", action="store_true",
                    help="include backend diagnostics for python -m race.monitor (opt-in)")
    args = ap.parse_args(argv)
    if (args.serial_debug or args.gdb_port is not None) and args.backend != "renode":
        ap.error("--serial-debug/--gdb-port require --backend renode")
    if args.gdb_port is not None and (not args.serve or not args.paused or args.all):
        ap.error("--gdb-port requires --serve --paused and a single task")
    if args.paused and (not args.serve or args.all):
        ap.error("--paused requires --serve and a single task")
    if args.monitor_stream and (not args.serve or args.all):
        ap.error("--monitor-stream requires --serve and a single task")

    if args.all:
        rows = []
        for task in sorted(tasks.TASKS):
            backend = None
            if args.backend == "hostc":
                backend = _hostc_backend(args, task)
                print(f"race: task {task} controller slot = {backend.name}")
            elif args.backend == "renode":
                backend = _firmware_backend(args, task)
                print(f"race: task {task} controller slot = {backend.name}")
            v = run_task(task, turbo=args.turbo, timeout=args.timeout,
                         verbose=args.verbose, backend=backend,
                         event_log=args.event_log, battery=args.battery)
            rows.append(v)
            print(json.dumps(v, ensure_ascii=False))
        print(f"\n{'task':>4} {'pass':>5} {'time':>7} {'limit':>6} "
              f"{'stop@':>6} {'beeps':>6}")
        for v in rows:
            lim = v["limit_s"] if v["limit_s"] else "-"
            el = f"{v['elapsed_s']:.2f}" if v["elapsed_s"] is not None else "-"
            print(f"{v['task']:>4} {str(v['pass']):>5} {el:>7} {lim:>6} "
                  f"{v['stop_dist_m']:>6.2f} {v['beep_seq_ok']!s:>6}")
        return 0 if all(v["pass"] for v in rows) else 1

    backend = None
    if args.backend == "hostc":
        backend = _hostc_backend(args, args.task)
        print(f"race: controller slot = {backend.name}")
    elif args.backend == "renode":
        backend = _firmware_backend(args, args.task)
        print(f"race: controller slot = {backend.name}")

    loop = RaceLoop(task=args.task, battery=args.battery,
                    turbo=args.turbo, controller=backend, event_log=args.event_log,
                    monitor_stream=args.monitor_stream)
    loop.paused = args.paused

    session = None
    if args.serve:
        from .serve import ServeSession, build_server
        server = build_server(args.port, args.monitor_stream)
        server.start()
        session = ServeSession(loop, server)
        print(f"race: websocket on ws://{server.host}:{server.port}; 3D view: "
              f"cd web && npm run dev, open "
              f"http://localhost:5173/?ws=ws://{server.host}:{server.port}")

    try:
        while True:
            verdict = loop.run_until_done(
                args.timeout or TIMEOUTS[loop.controller.task],
                realtime=args.realtime,
                on_state=session.on_state if session else None,
                progress_hz=1.0 if args.verbose or not args.serve else 0.0,
                on_command=session.pump if session else None)
            print(json.dumps(verdict, ensure_ascii=False))
            if session is None:
                break
            # keep the verdict on the wire: the web HUD shows the grade
            # banner until the next task/reset command. hold() keeps the
            # connection open (state at ~10 Hz, or the recorded cache
            # replaying at the viewer's chosen speed -- a player left
            # running from the mission's catch-up phase keeps playing,
            # now looping); the next task/reset command restarts the
            # run, Ctrl+C exits
            session.last_grade = verdict
            session.hold()
    except KeyboardInterrupt:
        print("\nrace: interrupted")
    finally:
        if session is not None:
            session.server.stop()
            time.sleep(0.1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
