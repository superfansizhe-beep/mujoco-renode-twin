"""ServeSession -- the --serve skeleton as one object.

The server, the loop, the replay cache/player and the restart/grade
bookkeeping live together here so the CLI (race/__main__.py) shrinks
to argparse + backend factories: run a mission with on_state wired to
the session, then hold() between missions (state at ~10 Hz, or the
recorded cache playing at the viewer's chosen speed) until the next
task/reset command.
"""
import time

from bot.server import BotServer

from .replay import ReplayCache, ReplayPlayer


def build_server(port: int, monitor_stream: bool = False) -> BotServer:
    from . import scene as scene_mod
    return BotServer(port=port, scene={
        "type": "scene", "app": "race",
        "monitor_stream": monitor_stream,
        "title": "Race Twin — 2024 H sheet",
        "track": scene_mod.payload()})


class ServeSession:
    """One viewer connection's server-side lifetime."""

    def __init__(self, loop, server: BotServer) -> None:
        self.loop = loop
        self.server = server
        self.cache = ReplayCache()
        self.player = ReplayPlayer(self.cache)
        self.restarts = 0
        self.last_grade = None   # the finished run's verdict, pushed with
                                 # the held states; cleared by task/reset

    def bump_restarts(self) -> None:
        self.restarts += 1

    # ---------------- run phase (on_state seam) ----------------
    def on_state(self, st: dict) -> None:
        self.cache.record(st)
        self.player.consume()
        out = self.player.advance(growing=True)
        if out is None:
            out = dict(st)
        out["rec"] = {"n": len(self.cache), "live": True}
        self.server.push_state(out)

    # ---------------- commands (on_command seam) ----------------
    def pump(self) -> None:
        loop = self.loop
        for _ in range(16):
            cmd = self.server.poll_command()
            if cmd is None:
                break
            ctype = cmd.get("type")
            if ctype == "task":
                # keep the server-side turbo default unless the client
                # explicitly chose one (set_task(turbo=None) preserves it)
                turbo = bool(cmd["turbo"]) if "turbo" in cmd else None
                loop.set_task(int(cmd.get("task", 2)), turbo=turbo)
                self.bump_restarts()
                self.last_grade = None
                self.cache.clear()
                self.player.stop()
            elif ctype == "reset":
                loop.reset()
                self.bump_restarts()
                self.last_grade = None
                self.cache.clear()
                self.player.stop()
            elif ctype == "pause":
                loop.paused = True
            elif ctype == "run":
                loop.paused = False
            elif ctype == "replay":
                # {"x": speed}: cache playback. Mid-run it plays catch-up
                # over the recorded prefix (the sim keeps recording) and
                # hands back to live at the live edge; in the hold phase
                # it loops the finished recording. A repeat updates the
                # speed without rewinding.
                try:
                    self.player.request(max(0.05, float(cmd.get("x", 1))))
                except (TypeError, ValueError):
                    pass
            elif ctype == "live":
                self.player.request(0.0)    # exit replay
            elif ctype == "serial":
                command = str(cmd.get("command", ""))
                try:
                    loop.controller.queue_debug_command(command)
                    loop.monitor.emit("serial.command_queued", loop.data.time,
                                      loop.last_motor.fw_seq, command=command)
                except (AttributeError, ValueError) as exc:
                    loop.monitor.emit("serial.command_rejected", loop.data.time,
                                      loop.last_motor.fw_seq, "warning", reason=str(exc))
            elif ctype == "snapshot":
                try:
                    loop.save_snapshot()
                except (OSError, ValueError) as exc:
                    loop.monitor.emit("snapshot.error", loop.data.time,
                                      loop.last_motor.fw_seq, "warning", reason=str(exc))

    # ---------------- hold phase ----------------
    def hold(self) -> None:
        """Keep the connection open between missions; returns when a
        task/reset command restarts the run (the caller re-runs)."""
        mark = self.restarts
        while self.restarts == mark:
            self.pump()
            self.player.consume()
            out = self.player.advance(growing=False)
            if out is not None:
                if self.last_grade:
                    out["grade"] = self.last_grade
                out["rec"] = {"n": len(self.cache), "live": False}
                self.server.push_state(out)
                time.sleep(1.0 / 30.0)
                continue
            st = self.loop.state()
            if self.last_grade:
                st["grade"] = self.last_grade
            st["rec"] = {"n": len(self.cache), "live": False}
            self.server.push_state(st)
            time.sleep(0.1)
