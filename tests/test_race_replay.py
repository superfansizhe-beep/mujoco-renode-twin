"""ReplayCache/ReplayPlayer unit gates -- synthetic frames, a frozen
clock, no server: the player semantics the e2e catch-up gate exercises
end to end (handoff at the live edge, hold-phase loop, speed change
without rewind) pinned here deterministically."""
import unittest
from unittest.mock import patch

from race.replay import ReplayCache, ReplayPlayer


def frame(n, t):
    return {"type": "state", "t": t, "n": n}


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now


class ReplayCacheTests(unittest.TestCase):
    def test_record_appends_monotonic_frames_and_drops_repeats(self):
        cache = ReplayCache()
        self.assertTrue(cache.record(frame(0, 0.0)))
        self.assertTrue(cache.record(frame(1, 0.1)))
        self.assertFalse(cache.record(frame(2, 0.1)))   # paused debugger
        self.assertFalse(cache.record(frame(3, 0.05)))  # going backwards
        self.assertEqual(len(cache), 2)

    def test_clear_empties_the_recording(self):
        cache = ReplayCache()
        cache.record(frame(0, 0.0))
        cache.clear()
        self.assertEqual(len(cache), 0)


class ReplayPlayerTests(unittest.TestCase):
    def setUp(self):
        self.cache = ReplayCache()
        for n, t in enumerate((0.0, 0.1, 0.2, 0.3, 0.4)):
            self.cache.record(frame(n, t))
        self.player = ReplayPlayer(self.cache)
        self.clock = FakeClock()
        patcher = patch("race.replay.time", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_live_view_returns_none_until_a_speed_is_requested(self):
        self.assertIsNone(self.player.advance(growing=True))

    def test_first_advance_pins_the_cursor_at_the_first_frame(self):
        self.player.request(2.0)
        self.player.consume()
        out = self.player.advance(growing=True)
        self.assertEqual(out["n"], 0)
        self.assertEqual(out["replay"], {"x": 2.0, "i": 0, "n": 5})

    def test_cursor_advances_by_wall_times_speed_and_never_rewinds_i(self):
        self.player.request(2.0)
        self.player.consume()
        self.player.advance(growing=True)          # wall pinned at 100.0
        self.clock.now = 100.08                    # +0.08 s wall -> +0.16 s t
        out = self.player.advance(growing=True)
        self.assertEqual(out["n"], 1)              # t=0.16 -> frame 1
        self.clock.now = 100.09                    # +0.01 s -> +0.02 s t=0.18
        out = self.player.advance(growing=True)
        self.assertEqual(out["n"], 1)              # still frame 1, i kept

    def test_speed_change_keeps_the_cursor_position(self):
        self.player.request(1.0)
        self.player.consume()
        self.player.advance(growing=True)
        self.clock.now = 100.15                    # t~0.15, i=1
        out = self.player.advance(growing=True)
        self.assertEqual(out["replay"]["i"], 1)
        self.player.request(8.0)
        self.player.consume()
        out = self.player.advance(growing=True)    # +0.00 s at the new speed
        self.assertEqual(out["replay"]["x"], 8.0)
        self.assertEqual(out["replay"]["i"], 1)    # no rewind on respeed

    def test_midrun_cursor_hands_back_to_live_at_the_edge(self):
        self.player.request(1000.0)                # far above any wall slop
        self.player.consume()
        self.player.advance(growing=True)          # pin
        self.clock.now = 100.01
        self.assertIsNone(self.player.advance(growing=True))
        self.assertIsNone(self.player.advance(growing=True))  # stays live

    def test_hold_phase_loops_at_the_tail(self):
        self.player.request(1000.0)
        self.player.consume()
        self.player.advance(growing=False)         # pin
        self.clock.now = 100.01                    # t races past 0.4 -> wrap
        out = self.player.advance(growing=False)
        self.assertEqual(out["n"], 0)
        self.assertEqual(out["replay"]["i"], 0)    # rewound for the loop

    def test_request_zero_exits_replay(self):
        self.player.request(2.0)
        self.player.consume()
        self.player.advance(growing=True)
        self.player.request(0.0)
        self.player.consume()
        self.assertIsNone(self.player.advance(growing=True))

    def test_stop_kills_the_cursor_like_a_task_switch(self):
        self.player.request(2.0)
        self.player.consume()
        self.player.advance(growing=True)
        self.player.stop()
        self.assertIsNone(self.player.advance(growing=True))

    def test_dying_cache_disarms_the_player(self):
        self.player.request(2.0)
        self.player.consume()
        self.player.advance(growing=True)
        self.cache.clear()
        self.assertIsNone(self.player.advance(growing=True))

    def test_requests_wait_for_consume_without_racing(self):
        self.player.request(2.0)                   # not consumed yet
        self.assertIsNone(self.player.advance(growing=True))


if __name__ == "__main__":
    unittest.main()
