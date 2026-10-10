"""Observability must preserve the coupling and fail closed on stale C state."""
import json
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from race.mailbox import RaceMotorFrame
from race.monitoring import RaceMonitor


class Monitoring(unittest.TestCase):
    def test_event_log_write_failure_does_not_interrupt_control(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = RaceMonitor(directory)  # writing a directory fails on every OS
            monitor.emit("control.running", .1, 20)
            self.assertEqual([e["kind"] for e in monitor.events],
                             ["control.running", "monitor.log_error"])
            self.assertIsNone(monitor.event_log)
            monitor.emit("control.running", .105, 21)
            self.assertEqual(monitor.events[-1]["fw_seq"], 21)
    def test_missing_symbol_file_reports_unavailable(self):
        from race.diagnostics import CEstimates
        snapshot = CEstimates("not-a-loaded-firmware.elf", read_word=lambda _: 0).snapshot(0, "arm")
        self.assertFalse(snapshot["available"])
        self.assertIn("reason", snapshot)

    def test_history_is_bounded_and_resets_have_distinct_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            monitor = RaceMonitor(path, capacity=4)
            for i in range(10):
                monitor.emit("sample", i * .005, i)
            snapshot = monitor.snapshot(.05, 10, False, False)
            self.assertEqual([e["seq"] for e in snapshot["events"]], [7, 8, 9, 10])
            self.assertEqual(snapshot["dropped_events"], 6)
            self.assertEqual(len([json.loads(line) for line in path.read_text().splitlines()]), 10)
            self.assertNotEqual(monitor.run_id, RaceMonitor().run_id)

    def test_sustained_alerts_do_not_flood_and_blind_legs_do_not_trigger_recovery(self):
        monitor = RaceMonitor()
        mission = {"phase": "run", "seg_i": 0, "seg": "AC", "lap": 1, "line_source": "hold"}
        for i in range(1, 401):
            monitor.observe(i * .005, RaceMotorFrame(fw_seq=i, duty_l=450), mission, True, .005, [])
        kinds = [e["kind"] for e in monitor.events]
        self.assertEqual(kinds.count("control.saturation"), 1)
        self.assertEqual(kinds.count("line.recovery_observed"), 2)
        mission["line_source"] = "sensor"
        monitor.observe(2.005, RaceMotorFrame(fw_seq=401), mission, True, .005, [])
        self.assertEqual(monitor.heartbeat_gaps, 0)
        kinds = [e["kind"] for e in monitor.events]
        self.assertEqual(kinds.count("line.recovery_ended"), 1)
        self.assertEqual(kinds.count("control.saturation_ended"), 1)
        blind = RaceMonitor()
        mission["line_source"] = "odometry"
        for i in range(1, 401):
            blind.observe(i * .005, RaceMotorFrame(fw_seq=i), mission, False, .005, [])
        self.assertNotIn("line.recovery_observed", [e["kind"] for e in blind.events])


class HostCMonitoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from bot.hostc import find_host_gcc
        if find_host_gcc() is None:
            raise unittest.SkipTest("host gcc unavailable")

    def test_snapshots_do_not_change_outputs_or_world_and_reject_stale_cycle(self):
        from race.hostc_backend import RaceHostcController
        from race.loop import RaceLoop
        ctl = RaceHostcController(task=2)
        loop = RaceLoop(task=2, controller=ctl)
        frames, monitored = [], []
        for _ in range(140):
            frames.append(loop.step_coupling())
            monitored.append(loop.last_motor)
            world, seq = loop.data.time, ctl.fw_seq
            snapshot = loop.state(include_debug=True)["debug"]["estimates"]
            self.assertTrue(snapshot["available"], snapshot)
            self.assertEqual(snapshot["fw_seq"], seq)
            self.assertEqual((world, seq), (loop.data.time, ctl.fw_seq))
        self.assertGreater(snapshot["pitch_deg"], 1.0, "must read real fused control state")
        self.assertFalse(ctl._estimates.snapshot(seq + 1, ctl.phase)["available"])
        self.assertFalse(ctl._estimates.snapshot(seq, "done")["available"])
        ctl.reset()
        unmonitored = [ctl.step(frame) for frame in frames]
        self.assertEqual(monitored, unmonitored, "reading snapshots changed C outputs")
        old_run = loop.monitor.run_id
        loop.reset()
        self.assertNotEqual(old_run, loop.monitor.run_id)
        self.assertEqual(loop.state(include_debug=True)["debug"]["estimates"]["fw_seq"], 0)
        world, seq = loop.data.time, ctl.fw_seq
        with tempfile.TemporaryDirectory() as folder:
            path = loop.save_snapshot(folder)
            saved = json.loads(Path(path).read_text())
            self.assertEqual(saved["debug"]["run_id"], loop.monitor.run_id)
            self.assertEqual(saved["debug"]["saved_snapshot"], str(Path(path).resolve()))
            self.assertEqual(saved["fw_seq"], seq)
            self.assertEqual((world, seq), (loop.data.time, ctl.fw_seq))

    def test_viewer_skips_symbol_reads_but_backend_events_and_exports_continue(self):
        from race.hostc_backend import RaceHostcController
        from race.loop import RaceLoop
        ctl = RaceHostcController(task=2)
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "events.jsonl"
            loop = RaceLoop(task=2, controller=ctl, event_log=log)
            with patch.object(ctl, "diagnostics", side_effect=AssertionError("viewer read C symbols")):
                for _ in range(65):
                    loop.step_coupling()
                self.assertNotIn("debug", loop.state())
                loop.paused = True
                loop.step_coupling()
                loop.paused = False
                loop.step_coupling()
            kinds = [json.loads(line)["kind"] for line in log.read_text().splitlines()]
            self.assertIn("mission.start", kinds)
            self.assertIn("simulation.paused", kinds)
            self.assertIn("simulation.resumed", kinds)
            self.assertTrue(loop.state(include_debug=True)["debug"]["estimates"]["available"])
            saved = json.loads(Path(loop.save_snapshot(folder)).read_text())
            self.assertTrue(saved["debug"]["estimates"]["available"])
            loop._monitor_stream = True
            self.assertIn("debug", loop.state())

    def test_terminal_client_controls_and_exports_actual_backend_without_a_viewer(self):
        import sys
        from websockets.asyncio.client import connect
        root = Path(__file__).resolve().parents[1]

        def client(url, command, *extra):
            return subprocess.run([sys.executable, "-m", "race.monitor", command,
                                   "--url", url, "--timeout", "5", *extra],
                                  cwd=root, capture_output=True, text=True, timeout=12)

        async def first_state(url):
            async with connect(url) as ws:
                async with asyncio.timeout(5):
                    while True:
                        frame = json.loads(await ws.recv())
                        if frame["type"] == "state":
                            return frame

        with tempfile.TemporaryDirectory() as folder:
            for enabled in (False, True):
                with socket.socket() as free:
                    free.bind(("127.0.0.1", 0))
                    port = free.getsockname()[1]
                url = f"ws://127.0.0.1:{port}"
                log = Path(folder) / f"events-{enabled}.jsonl"
                command = [sys.executable, "-m", "race", "--backend", "hostc",
                           "--task", "2", "--serve", "--paused", "--realtime",
                           "--port", str(port), "--event-log", str(log)]
                if enabled:
                    command.append("--monitor-stream")
                with (Path(folder) / f"server-{enabled}.log").open("w") as output:
                    proc = subprocess.Popen(command, cwd=root, stdout=output, stderr=output)
                    try:
                        deadline = time.monotonic() + 15
                        while True:
                            try:
                                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                                    break
                            except OSError:
                                self.assertIsNone(proc.poll(), "backend exited during startup")
                                if time.monotonic() >= deadline:
                                    self.fail("backend listener did not start")
                                time.sleep(.05)
                        state = asyncio.run(first_state(url))
                        self.assertEqual("debug" in state, enabled)
                        result = client(url, "inspect")
                        if not enabled:
                            self.assertEqual(result.returncode, 1, result.stderr)
                            self.assertIn("--monitor-stream", result.stderr)
                            continue
                        self.assertEqual(result.returncode, 0, result.stderr)
                        state = json.loads(result.stdout)
                        self.assertTrue(state["paused"])
                        self.assertEqual(state["fw_seq"], 0)
                        result = client(url, "snapshot")
                        self.assertEqual(result.returncode, 0, result.stderr)
                        saved_path = Path(json.loads(result.stdout)["details"]["path"])
                        self.addCleanup(saved_path.unlink, missing_ok=True)
                        saved = json.loads(saved_path.read_text())
                        self.assertTrue(saved["debug"]["estimates"]["available"])
                        self.assertEqual(saved["fw_seq"], 0)
                        rejected = client(url, "ping")
                        self.assertEqual(rejected.returncode, 1)
                        self.assertIn("--serial-debug", rejected.stderr)
                        for control in ("run", "pause"):
                            result = client(url, control)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertEqual(json.loads(result.stdout)["paused"], control == "pause")
                        result = client(url, "events", "--duration", ".2")
                        self.assertEqual(result.returncode, 0, result.stderr)
                        events = [json.loads(line) for line in result.stdout.splitlines()]
                        seqs = [event["seq"] for event in events if "seq" in event]
                        self.assertEqual(len(seqs), len(set(seqs)), "held frames duplicated events")
                        self.assertIn("snapshot.saved", [event["kind"] for event in events])
                        self.assertIn("simulation.resumed", [event["kind"] for event in events])
                        self.assertTrue(log.is_file())
                    finally:
                        # Windows venv python.exe launches an interpreter child;
                        # terminate the owned tree so no listener/log handle leaks.
                        if sys.platform == "win32":
                            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                           capture_output=True, timeout=10)
                        else:
                            proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)


class RenodeMonitoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_race_firmware import _renode_ready
        ready, reason = _renode_ready()
        if not ready:
            raise unittest.SkipTest(reason)

    def test_serial_commands_and_symbol_reads_preserve_lockstep_and_gdb_reads_paused_board(self):
        from race.loop import RaceLoop
        from race.renode_backend import RacePeriphBackend
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            port = free.getsockname()[1]
        fw = RacePeriphBackend(task=2, uart_telemetry=True, gdb_port=port)
        self.addCleanup(fw._ch.emu.clear)
        loop = RaceLoop(task=2, controller=fw)
        for i in range(140):
            if i == 70:
                fw.queue_debug_command("ping")
                with self.assertRaises(ValueError):
                    fw.queue_debug_command("stat")
            if i == 100:
                fw.queue_debug_command("stat")
            loop.step_coupling()
            if i % 7 == 0:
                snapshot = loop.state(include_debug=True)["debug"]
                self.assertTrue(snapshot["estimates"]["available"], snapshot)
                self.assertEqual(snapshot["estimates"]["fw_seq"], i + 1)
            self.assertEqual(fw.fw_seq, i + 1, "debugging duplicated or skipped a control cycle")
        snapshot = loop.state(include_debug=True)["debug"]
        self.assertIn("pong", [e["text"] for e in snapshot["serial"]["events"]])
        self.assertTrue(snapshot["serial"]["latest_telemetry"].startswith("T "))
        replies = {e["details"].get("command"): e for e in loop.monitor.events if e["kind"] == "serial.rx"}
        self.assertEqual(replies["ping"]["details"]["text"], "pong")
        self.assertTrue(replies["stat"]["details"]["text"].startswith("T "))
        self.assertIsNone(snapshot["serial"]["pending_command"])
        self.assertEqual(snapshot["heartbeat_gaps"], 0)
        with self.assertRaises(ValueError):
            fw.queue_debug_command("continue")
        loop.paused = True
        world, seq = loop.data.time, fw.fw_seq
        gdb = Path(os.getenv("ARM_GDB")
                   or __import__("shutil").which("arm-none-eabi-gdb") or "")
        self.assertTrue(gdb.is_file(), "GDB executable required for this inspection gate")
        result = subprocess.run([str(gdb), "--batch", fw._elf_path,
                                 "-ex", f"target remote 127.0.0.1:{port}",
                                 "-ex", "x/wx &law_seq", "-ex", "detach"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"0x{seq:08x}", result.stdout, result.stdout)
        self.assertFalse(fw._ch.emu.internal.IsStarted,
                         "GDB attach/detach started the emulation outside coupling")
        loop.step_coupling()
        self.assertEqual((world, seq), (loop.data.time, fw.fw_seq))
        loop.paused = False
        loop.step_coupling()
        self.assertEqual(fw.fw_seq, seq + 1, "board did not resume lockstep after GDB detach")
        self.performance_evidence = {"couplings": seq, "world_s": world,
                                     "snapshot": snapshot, "gdb_output": result.stdout}
        loop.reset()  # clear the old GDB listener and bind the new cold-boot machine
        loop.paused = True
        result = subprocess.run([str(gdb), "--batch", fw._elf_path,
                                 "-ex", f"target remote 127.0.0.1:{port}",
                                 "-ex", "x/wx &law_seq", "-ex", "detach"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0x00000000", result.stdout, result.stdout)
        self.assertEqual(loop.data.time, 0)
        self.performance_evidence["gdb_after_reset"] = result.stdout
