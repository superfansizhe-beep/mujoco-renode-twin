"""ops.py -- one small manager for the twin's dev services.

  python ops.py status
  python ops.py start viewer [twin] [race [--task N] [--backend hostc]]
  python ops.py stop [all|viewer|twin|race] | --port N [--force]
  python ops.py logs viewer|twin|race [-n 40]

Services are identified by FIXED ports (viewer 5173 vite --strictPort,
twin 8765, race 8766) -- vite drifting to 5174..5179 across sessions is
how the machine ended up with seven orphaned dev servers. stop kills
whatever LISTENS on the port, wrapper children and orphans included
(taskkill /T), but only python.exe/node.exe images unless --force.
Logs append to output/ops/<svc>.log; services run detached.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
OPS = REPO / "output" / "ops"

# svc -> (port, ready-timeout s)
SERVICES = {"viewer": (5173, 20.0), "twin": (8765, 15.0), "race": (8766, 20.0)}
RENODE_READY_S = 90.0          # cold boot + ELF load
OUR_IMAGES = {"python.exe", "node.exe"}

DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def listener_pids(port: int) -> list[int]:
    out = _run(["netstat", "-ano", "-p", "tcp"]).stdout
    pids = []
    for line in out.splitlines():
        f = line.split()
        if (len(f) == 5 and f[0] == "TCP" and f[3] == "LISTENING"
                and f[1].endswith(f":{port}")):
            pids.append(int(f[4]))
    return sorted(set(pids))


def image_name(pid: int) -> str | None:
    out = _run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]).stdout
    for line in out.splitlines():
        f = [c.strip('"') for c in line.split('","')]
        if len(f) >= 2 and f[1] == str(pid):
            return f[0].lower()
    return None


def all_listeners() -> dict[int, int]:
    """Port -> pid for every LISTEN in the dev ranges (stray hunting)."""
    out = _run(["netstat", "-ano", "-p", "tcp"]).stdout
    found = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) != 5 or f[0] != "TCP" or f[3] != "LISTENING":
            continue
        try:
            port = int(f[1].rsplit(":", 1)[1])
            pid = int(f[4])
        except ValueError:
            continue
        if 5170 <= port <= 5189 or 8760 <= port <= 8779:
            found[port] = pid
    return dict(sorted(found.items()))


def descends_from(pid: int, root: int) -> bool:
    """True if pid's parent chain reaches root. The venv python.exe is a
    redirector: the real interpreter (the actual listener) is its child."""
    for _ in range(5):
        if pid == root:
            return True
        out = _run(["powershell", "-NoProfile", "-Command",
                    f"(Get-CimInstance Win32_Process "
                    f"-Filter 'ProcessId={pid}').ParentProcessId"]).stdout
        try:
            pid = int(out.strip())
        except ValueError:
            return False
    return False


def start_service(svc: str, args) -> bool:
    port, ready_s = SERVICES[svc]
    if getattr(args, "port", None):
        port = args.port        # isolated gates only; everyone else
                                # keeps the canonical port
    pids = listener_pids(port)
    if pids:
        print(f"{svc}: already up on :{port} (pid {' '.join(map(str, pids))})")
        return True
    OPS.mkdir(parents=True, exist_ok=True)
    log = open(OPS / f"{svc}.log", "ab")
    log.write(f"\n===== ops start {time.strftime('%Y-%m-%d %H:%M:%S')} "
              f"=====\n".encode())
    log.flush()
    if svc == "viewer":
        vite = REPO / "web" / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite.exists():
            print("viewer: web/node_modules missing -- cd web && npm install")
            return False
        cmd = ["node", str(vite), "--port", str(port), "--strictPort"]
        cwd = REPO / "web"
    else:
        cmd = [sys.executable, "-u", "-m", svc, "--serve",
               "--port", str(port)]
        if svc == "race":
            cmd += ["--task", str(args.task), "--backend", args.backend]
            if args.backend == "hostc":
                cmd.append("--realtime")  # native C can outrun the world clock
            if args.backend == "renode":
                ready_s = RENODE_READY_S
        else:
            cmd += ["--balance", "--realtime"]
        cwd = REPO
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=log,
                            stderr=subprocess.STDOUT,
                            creationflags=DETACHED, stdin=subprocess.DEVNULL)
    log.close()
    def bail(msg):
        print(f"{svc}: {msg} -- last log lines (python ops.py logs {svc}):")
        tail = (OPS / f"{svc}.log").read_bytes().decode(errors="replace")
        for line in tail.splitlines()[-5:]:
            print(f"  {line}")
        return False
    deadline = time.monotonic() + ready_s
    while time.monotonic() < deadline:
        pids = listener_pids(port)
        if pids:
            # the listener must belong to the process we spawned -- a
            # stranger on the port is a collision; say so, don't adopt it
            if not any(descends_from(p, proc.pid) for p in pids):
                img = image_name(pids[0]) or "?"
                print(f"{svc}: :{port} held by pid {pids[0]} ({img}), "
                      f"NOT our serve (pid {proc.pid}) -- fix that first")
                return False
            time.sleep(2.0)      # survived past bind? (silent-death guard)
            if proc.poll() is not None:
                return bail(f"exited rc={proc.poll()} right after "
                            f"binding :{port}")
            print(f"{svc}: up on :{port} pid {pids[0]} "
                  f"(log output/ops/{svc}.log)")
            return True
        if proc.poll() is not None:
            return bail(f"exited rc={proc.poll()} before binding :{port}")
        time.sleep(0.5)
    return bail(f"NOT ready within {ready_s:.0f}s")


def stop_port(port: int, force: bool) -> bool:
    pids = listener_pids(port)
    if not pids:
        print(f":{port}: nothing listening")
        return True
    for pid in pids:
        img = image_name(pid)
        if img not in OUR_IMAGES and not force:
            print(f":{port}: pid {pid} is {img or 'gone'} -- not ours, "
                  f"refusing (use --force)")
            return False
        _run(["taskkill", "/PID", str(pid), "/T", "/F"])
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and listener_pids(port):
        time.sleep(0.25)
    if listener_pids(port):
        print(f":{port}: still listening after kill")
        return False
    print(f":{port}: stopped ({' '.join(map(str, pids))})")
    return True


def cmd_status(_args) -> int:
    running = {}
    for svc, (port, _) in SERVICES.items():
        pids = listener_pids(port)
        if pids:
            img = image_name(pids[0]) or "?"
            running[svc] = pids[0]
            print(f"{svc:>7}  :{port}  UP   pid {pids[0]} ({img})")
        else:
            print(f"{svc:>7}  :{port}  down")
    for port, pid in all_listeners().items():
        if port in {p for p, _ in SERVICES.values()}:
            continue
        img = image_name(pid) or "?"
        print(f"  stray  :{port}  pid {pid} ({img})  "
              f"-- python ops.py stop --port {port}")
    if "viewer" in running:
        for svc in ("race", "twin"):
            if svc in running:
                print(f"open http://localhost:5173/?ws=ws://127.0.0.1:"
                      f"{SERVICES[svc][0]}")
    return 0


def cmd_start(args) -> int:
    if args.port and len(args.services) != 1:
        print("--port needs exactly one service")
        return 1
    todo = [s for s in args.services if s in SERVICES]
    ok = all(start_service(s, args) for s in todo)
    if ok and "viewer" in todo:
        for svc in ("race", "twin"):
            if svc in todo or listener_pids(SERVICES[svc][0]):
                print(f"open http://localhost:5173/?ws=ws://127.0.0.1:"
                      f"{SERVICES[svc][0]}")
                break
    return 0 if ok else 1


def cmd_stop(args) -> int:
    if args.port:
        return 0 if stop_port(args.port, args.force) else 1
    names = args.services or ["all"]
    ports = ([p for s, (p, _) in SERVICES.items()
              if s in names or "all" in names])
    return 0 if all(stop_port(p, args.force) for p in ports) else 1


def cmd_logs(args) -> int:
    path = OPS / f"{args.service}.log"
    if not path.exists():
        print(f"{args.service}: no log yet ({path})")
        return 1
    lines = path.read_bytes().decode(errors="replace").splitlines()
    for line in lines[-args.n:]:
        print(line)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ops", description=__doc__,
                                 formatter_class=argparse.
                                 RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="ports, pids, strays").set_defaults(
        func=cmd_status)

    p = sub.add_parser("start", help="start services (detached, logged)")
    p.add_argument("services", nargs="+", choices=tuple(SERVICES))
    p.add_argument("--task", type=int, default=1,
                   help="race: starting task (default 1)")
    p.add_argument("--backend", choices=("stub", "hostc", "renode"), default="hostc",
                   help="race: controller slot (default host-compiled C law)")
    p.add_argument("--port", type=int, default=None,
                   help="single service only: override its fixed port "
                        "(isolated gates)")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="stop by service/port (tree-kill)")
    p.add_argument("services", nargs="*",
                   choices=(*SERVICES, "all"))
    p.add_argument("--port", type=int, default=None,
                   help="stop whatever listens here (orphans included)")
    p.add_argument("--force", action="store_true",
                   help="kill even non-python/node listeners")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("logs", help="tail a service log")
    p.add_argument("service", choices=tuple(SERVICES))
    p.add_argument("-n", type=int, default=40, help="last N lines")
    p.set_defaults(func=cmd_logs)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
