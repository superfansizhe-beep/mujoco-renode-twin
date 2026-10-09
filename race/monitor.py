"""Backend diagnostic client. JSON output, no viewer or extra control cycles."""
import argparse
import asyncio
import json
import sys

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


def _write(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


async def _state(ws):
    while True:
        frame = json.loads(await ws.recv())
        if frame.get("type") == "scene":
            if frame.get("app") != "race" or not frame.get("monitor_stream"):
                raise ValueError("start the race backend with --serve --monitor-stream")
        elif frame.get("type") == "state" and not frame.get("replay"):
            if "debug" not in frame:
                raise ValueError("backend diagnostics are disabled; use --monitor-stream")
            return frame


async def run(args):
    async with connect(args.url, open_timeout=args.timeout) as ws:
        async with asyncio.timeout(args.timeout):
            initial = await _state(ws)
        if args.command == "inspect":
            _write(initial)
            return
        if args.command == "events":
            run_id, seq = None, 0
            frame = initial
            deadline = asyncio.get_running_loop().time() + args.duration if args.duration else None
            while True:
                debug = frame["debug"]
                if debug["run_id"] != run_id:
                    run_id, seq = debug["run_id"], 0
                if debug["first_seq"] > seq + 1:
                    _write({"kind": "monitor.history_gap", "run_id": run_id,
                            "missed_events": debug["first_seq"] - seq - 1})
                for event in debug["events"]:
                    if event["seq"] > seq:
                        _write(event)
                        seq = event["seq"]
                try:
                    async with asyncio.timeout_at(deadline):
                        frame = await _state(ws)
                except TimeoutError:
                    if deadline is not None:
                        return
                    raise
        else:
            if args.command in ("ping", "stat"):
                serial = initial["debug"]["serial"]
                if not serial or not serial["enabled"]:
                    raise ValueError("serial capture disabled; also launch with --serial-debug")
                if initial["paused"]:
                    raise ValueError("serial replies require normal coupled steps; resume with race.monitor run")
                command = {"type": "serial", "command": args.command}
            else:
                command = {"type": args.command}
            await ws.send(json.dumps(command))
            anchor = initial["debug"]["last_seq"]
            async with asyncio.timeout(args.timeout):
                while True:
                    frame = await _state(ws)
                    debug = frame["debug"]
                    if debug["run_id"] != initial["debug"]["run_id"]:
                        raise ValueError("simulation reset while awaiting the command result")
                    if args.command in ("pause", "run") and frame["paused"] == (args.command == "pause"):
                        _write({"paused": frame["paused"], "world_s": frame["t"], "fw_seq": frame["fw_seq"]})
                        return
                    for event in debug["events"]:
                        if event["seq"] <= anchor:
                            continue
                        kind = event["kind"]
                        if kind in ("snapshot.error", "serial.command_rejected"):
                            raise ValueError(event["details"]["reason"])
                        if args.command == "snapshot" and kind == "snapshot.saved":
                            _write(event)
                            return
                        if args.command in ("ping", "stat") and kind == "serial.rx":
                            if event["details"].get("command") == args.command:
                                _write(event)
                                return


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("events", "inspect", "snapshot", "ping", "stat", "pause", "run"), default="events", nargs="?")
    ap.add_argument("--url", default="ws://127.0.0.1:8766")
    ap.add_argument("--timeout", type=float, default=30, help="connection/command timeout in wall seconds")
    ap.add_argument("--duration", type=float, help="stop event capture after these wall seconds")
    args = ap.parse_args(argv)
    if args.timeout <= 0 or (args.duration is not None and args.duration <= 0):
        ap.error("timeout and duration must be positive")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TimeoutError, ConnectionClosed) as exc:
        print(f"race-monitor: {exc or 'timed out waiting for backend'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
