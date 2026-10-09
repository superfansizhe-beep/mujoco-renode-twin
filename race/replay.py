"""The record/replay cache -- the viewer-agnostic player.

Every pushed state lands in a per-mission recording (the replay
cache); live view records for free. The player walks that recording on
the wall clock: mid-run (growing) it plays catch-up over the recorded
prefix and hands back to live at the frontier -- the future is not
simulated yet, playback can only catch up; in the hold phase the
recording is complete and the cursor loops at the tail.
"""
import time


class ReplayCache:
    """This mission's recorded state stream."""

    def __init__(self) -> None:
        self.frames: list[dict] = []

    def record(self, st: dict) -> bool:
        """Append a frame unless the world pose repeats -- a debugger
        may inspect a paused board for minutes; its live events stay
        on the wire without recording identical poses forever."""
        if self.frames and st["t"] <= self.frames[-1]["t"] + 1e-9:
            return False
        self.frames.append(st)
        return True

    def clear(self) -> None:
        self.frames.clear()

    def __len__(self) -> int:
        return len(self.frames)


class ReplayPlayer:
    """Wall-anchored cursor over a ReplayCache: the active player is
    {"x", "t", "wall", "i"} -- t = virtual cursor, i = frame index that
    only moves forward (rewinds on loop)."""

    def __init__(self, cache: ReplayCache) -> None:
        self.cache = cache
        self._req = None          # pending {"x": speed} from the viewer
        self._rep = None          # the active cursor

    def request(self, x: float) -> None:
        """Queue a speed change ({"x": 0} exits replay)."""
        self._req = {"x": x}

    def stop(self) -> None:
        """Kill the active cursor (task/reset: the cache died)."""
        self._rep = None

    def consume(self) -> None:
        req = self._req
        if req is None:
            return
        self._req = None
        if req["x"] <= 0:
            self._rep = None                    # back to live view
        elif self._rep is None and self.cache.frames:
            self._rep = {"x": req["x"], "t": self.cache.frames[0]["t"],
                         "wall": None, "i": 0}
        elif self._rep is not None:
            self._rep["x"] = req["x"]           # speed change, no rewind

    def advance(self, growing: bool):
        """Step the cursor by wall * speed and return the frame to
        push, or None for live view. Mid-run (growing) the cursor hands
        back to live at the live edge -- the future is not simulated
        yet, playback can only catch up; in the hold phase the
        recording is complete and the cursor loops at the tail."""
        frames = self.cache.frames
        if not frames:
            self._rep = None     # the cache died under us (task/reset)
            return None
        r = self._rep
        if r is None:
            return None
        now = time.monotonic()
        if r["wall"] is not None:
            r["t"] += (now - r["wall"]) * r["x"]
        r["wall"] = now
        if r["t"] >= frames[-1]["t"]:
            if growing:
                self._rep = None
                return None
            r["t"] = frames[0]["t"]
            r["i"] = 0
        while (r["i"] + 1 < len(frames)
               and frames[r["i"] + 1]["t"] <= r["t"]):
            r["i"] += 1
        st = dict(frames[r["i"]])
        st["replay"] = {"x": r["x"], "i": r["i"], "n": len(frames)}
        return st
