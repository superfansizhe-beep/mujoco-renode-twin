"""Twin CLI.

  python -m twin --balance --serve --realtime     # the demo: web view
  python -m twin --balance --seconds 8            # headless regression
  python -m twin --drive --duty 300 --seconds 2   # chain check

With --serve, a WebSocket server on 127.0.0.1:8765 streams state at
30 Hz and accepts nudge/reset/pause/run/mode commands (bot.server).
"""
import argparse
import os
import sys
import time

from bot.loop import COUPLING_S
from bot import motors

from .loop import TwinLoop


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="twin")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--balance", action="store_true",
                      help="LQR stub controller balancing (default)")
    mode.add_argument("--drive", action="store_true",
                      help="constant duty both wheels (chain check)")
    ap.add_argument("--duty", type=int, default=300,
                    help="drive mode duty in permille (default 300)")
    ap.add_argument("--battery", choices=sorted(motors.BATTERY_NOMINAL),
                    default="3s")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="virtual seconds to run (0 = forever)")
    ap.add_argument("--serve", action="store_true",
                    help="run the WebSocket state server on :8765")
    ap.add_argument("--port", type=int, default=8765,
                    help="websocket port for --serve (ops.py routes "
                         "isolated gates through this)")
    ap.add_argument("--realtime", action="store_true",
                    help="pace to wall clock (for viewing)")
    ap.add_argument("--nudge-after", type=float, default=0.0, metavar="S",
                    help="fire a pitch kick at t=S (demo helper)")
    ap.add_argument("--backend", choices=("stub", "hostc", "renode"),
                    default="stub",
                    help="controller slot: python stub, the host-compiled "
                         "C core (firmware/core/balance.c, needs a host "
                         "gcc), or real C firmware in Renode behind its "
                         "peripheral path (needs the [renode] extra)")
    fw_default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "firmware", "twin", "balance_fw.elf")
    ap.add_argument("--firmware", default=fw_default,
                    metavar="ELF", help="firmware for --backend renode")
    args = ap.parse_args(argv)

    mode_name = "drive" if args.drive else "balance"
    if mode_name == "drive" and args.backend != "stub":
        ap.error("--drive has no firmware counterpart: the C core "
                 "implements balance only")
    backend = None
    if args.backend == "hostc":
        from bot.hostc import HostBalanceController
        backend = HostBalanceController()
    elif args.backend == "renode":
        from .renode_backend import RenodePeriphBackend
        backend = RenodePeriphBackend(
            elf_path=os.path.abspath(args.firmware), dt=COUPLING_S)
    loop = TwinLoop(mode=mode_name, battery=args.battery,
                    drive_duty=args.duty, controller=backend)
    trim = getattr(loop.controller, "theta_ref", None)
    print(f"twin: mode={loop.controller.name} battery={loop.v_batt} V"
          + (f" trim={trim * 57.2958:+.2f} deg" if trim is not None else ""))

    server = None
    on_state = None
    if args.serve:
        from bot.server import BotServer
        server = BotServer(port=args.port,
                           scene={"type": "scene", "app": "twin",
                                  "title": "Balance Twin"})
        server.start()
        on_state = server.push_state
        print(f"twin: websocket state stream on ws://{server.host}:{server.port}")

    def pump_commands():
        if server is None:
            return
        for _ in range(16):
            cmd = server.poll_command()
            if cmd is None:
                break
            ctype = cmd.get("type")
            if ctype == "nudge":
                loop.nudge(fx=float(cmd.get("fx", 0.0)),
                           fy=float(cmd.get("fy", 0.0)),
                           tx=float(cmd.get("tx", 0.0)))
            elif ctype == "reset":
                loop.reset()
            elif ctype == "pause":
                loop.paused = True
            elif ctype == "run":
                loop.paused = False
            elif ctype == "mode":
                try:
                    loop.set_mode(cmd.get("mode", "balance"),
                                  int(cmd.get("duty", args.duty)))
                except ValueError:
                    pass

    print_period = 1.0   # console heartbeat
    try:
        t_mark, print_mark = 0.0, 0.0
        while args.seconds <= 0 or loop.data.time < args.seconds:
            if args.nudge_after and loop.data.time >= args.nudge_after:
                loop.nudge(tx=3.5)
                args.nudge_after = 0.0
            # state_hz above the wire's 30 Hz: the firmware backend's
            # steps run ~25 ms wall (slower than realtime), and a lower
            # push gate skips steps -- the viewer then sees half the
            # wire rate (same rationale as race/loop.py)
            loop.run(0.1, realtime=args.realtime, on_state=on_state,
                     state_hz=60.0, on_step=pump_commands)
            if loop.data.time - print_mark >= print_period:
                st = loop.state()
                print(f"t={st['t']:6.2f} tilt={st['tilt_deg']:+6.2f} "
                      f"y={st['pos'][1]:+.3f} v={st['speed_mps']:+.3f} "
                      f"duty={st['duty'][0]:+5d} enc={st['enc'][0]:6d} "
                      + (f"fw_seq={st['fw_seq']} " if st["fw_seq"] else "")
                      + ("PAUSED" if st["paused"] else ""))
                print_mark = loop.data.time
    except KeyboardInterrupt:
        print("\ntwin: interrupted")
    finally:
        if server is not None:
            server.stop()
            time.sleep(0.1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
