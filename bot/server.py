"""WebSocket bridge: bot loop -> web frontend, commands the other way.

Threaded design: the bot loop owns MuJoCo in the MAIN thread; this
server runs its own asyncio loop in a daemon thread and talks to the
loop through two thread-safe queues (states out, commands in). The
loop pushes states at its broadcast rate; the server forwards only the
LATEST one to every client (video-style, no backlog).

Message protocol (JSON):
  server -> client:  a scene frame once per connection (the first
                     message; the app's identity + static scene data,
                     e.g. race embeds the whole track payload), then
                     state frames (schema: bot.telemetry), ~30 Hz
  client -> server:  app-specific command dicts, relayed verbatim:
                     twin:  {"type": "nudge", "fx": N, "fy": N, "tx": N*m}
                            {"type": "reset"} | {"type": "pause"} |
                            {"type": "run"} |
                            {"type": "mode", "mode": "balance"|"drive", "duty": p}
                     race:  {"type": "task", "task": 1-4, "turbo"?: bool} +
                            the shared reset/pause/run
"""
import asyncio
import json
import queue
import sys
import threading
import time

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


def _win_timer_period(ms: int) -> None:
    """Windows: asyncio.sleep quantizes to the system timer (~15.6 ms),
    which stretches the 30 Hz broadcast to ~21 Hz -- measured 2026-10-01.
    Ask for finer resolution for this process's lifetime."""
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.winmm.timeBeginPeriod(ms)
        except Exception:
            pass    # best effort; the quantization merely returns


class BotServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765,
                 scene: dict | None = None) -> None:
        self.host, self.port = host, port
        # the app's identity frame, sent as each client's first message
        # (set before start(); static for the server's lifetime)
        self.scene = scene
        self.states: "queue.Queue[dict]" = queue.Queue(maxsize=4)
        self.commands: "queue.Queue[dict]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = asyncio.Event()
        self.client_count = 0

    # ---- called from the bot loop thread ----
    def push_state(self, state: dict) -> None:
        try:
            self.states.put_nowait(state)
        except queue.Full:
            try:
                self.states.get_nowait()
                self.states.put_nowait(state)
            except queue.Empty:
                pass

    def poll_command(self) -> dict | None:
        try:
            return self.commands.get_nowait()
        except queue.Empty:
            return None

    # ---- lifecycle ----
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)

    def _run(self) -> None:
        _win_timer_period(1)
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        clients: set = set()

        async def handler(ws):
            self.client_count += 1
            clients.add(ws)
            try:
                if self.scene is not None:
                    await ws.send(json.dumps(self.scene))
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(msg, dict) and "type" in msg:
                        self.commands.put_nowait(msg)
            except ConnectionClosed:
                pass    # sleep-killed / half-open sockets: the client retries
            finally:
                clients.discard(ws)
                self.client_count -= 1

        async def broadcaster():
            next_tick = time.monotonic()
            while not self._stop.is_set():
                next_tick += 1.0 / 30.0
                delay = next_tick - time.monotonic()
                if delay < -0.2:
                    next_tick = time.monotonic()   # re-anchor after a stall
                else:
                    await asyncio.sleep(max(delay, 0.0))
                latest = self._latest_state()
                if latest is None or not clients:
                    continue
                raw = json.dumps(latest)
                for ws in list(clients):
                    try:
                        await ws.send(raw)
                    except Exception:
                        clients.discard(ws)

        try:
            async with serve(handler, self.host, self.port, max_size=1 << 16):
                await asyncio.ensure_future(broadcaster())
                await self._stop.wait()
        except OSError as exc:
            print(f"[bot-server] cannot listen on {self.host}:{self.port}: "
                  f"{exc}")

    def _latest_state(self) -> dict | None:
        latest = None
        try:
            while True:
                latest = self.states.get_nowait()
        except queue.Empty:
            return latest
