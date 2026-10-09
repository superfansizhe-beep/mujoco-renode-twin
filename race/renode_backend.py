"""RaceFirmwareBackend -- the REAL exam firmware in the controller slot.

Same channel and discipline as twin.renode_backend (bot.renode's
RenodeChannel: harness-owned sensor words -> RunFor(5 ms) -> motor/
status words back). The firmware (firmware/race/main.c) is line-by-line
isomorphic with the Python stub race/controller.py -- the A/B cross-check
is the port-correctness proof, the same gate the balance twin passed at
0.00 deg / 0.0 cm.

The controller's INTERNALS (phase machine, node beeps, odo) live in the
ELF; the harness observes them through the RAC2 status words -- phase/
seg_i at +0x30, mission clock at +0x34, e_lat/v_plan/odo telemetry.
Events are synthesized from buzzer rising edges in route order (beeps
fire in route order by construction), which is what the grader scores:
the REAL firmware's observable behavior, not the stub's dataclasses.
The mission surface both backends share (routes/task word/events/info)
is RaceMissionCore (race/mission.py).
"""
import os

import time

from bot.renode import (BOOT_TIMEOUT_WALL_S, BOOT_WINDOW_S,
                        RenodeChannel)

from . import mailbox
from .mailbox import (
    MAGIC, RACE_BASE, RaceMotorFrame, RaceSensorFrame, pack_sensors,
)
from .mission import RaceMissionCore

DEFAULT_ELF = os.path.join(
    os.path.dirname(__file__), "..", "firmware", "race", "race_fw.elf")


class RaceFirmwareBackend(RaceMissionCore):
    """The controller surface (task/turbo/phase/events/step/reset/info)
    backed by the C firmware in Renode instead of the Python stub."""

    name = "fw[race_fw.elf]"

    def __init__(self, task: int = 2, dt: float = 0.005,
                 v_batt: float = 11.1, turbo: bool | None = None,
                 elf_path: str | None = None, renode_path: str | None = None,
                 mips: int = 4) -> None:
        super().__init__(task, dt, turbo)
        self.v_batt = v_batt          # firmware reads the mailbox instead
        self._elf_path = os.path.abspath(elf_path or DEFAULT_ELF)
        self._ch: RenodeChannel | None = None
        self._mips = mips
        self._renode_path = renode_path
        self._booted = False          # first REAL frame still pending
        self.reset()

    # ---------------- lifecycle ----------------
    def reset(self, x0: float = 0.0, y0: float = 0.0,
              psi0: float = 0.0) -> None:
        """Full cold boot: fresh machine + fresh mission. (x0, y0, psi0)
        -- the spawn prior the stub gets -- is IGNORED: the firmware
        derives the identical triple from its own route table (both are
        'node A + first-segment tangent', race.spawn.spawn_for_task)."""
        del x0, y0, psi0                 # the harness passes them; fw owns them
        if self._ch is not None:
            self._ch.emu.clear()
        self._reset_mission()
        ch = RenodeChannel(self._elf_path, self.dt, mips=self._mips,
                           mach_name="race", renode_path=self._renode_path)
        self._ch = ch
        ch.write_word(RACE_BASE, MAGIC)
        frame = RaceSensorFrame(seq=1, task=self._task_word())
        words = pack_sensors(frame)
        for i in range(1, 9):      # seq..line_bits/task: harness-owned words
            ch.write_word(RACE_BASE + 4 * i, words[i])
        # Boot window runs the firmware's STARTUP only (vector table,
        # mission_init, seq baseline). NO strobe here: the balance twin
        # strobes a zeros frame and lets cycle 1 run on it -- the filter
        # then initializes theta at atan2(0,0)=0 instead of the spawn
        # trim, and the arm phase balances on a wrong lean (measured:
        # +0.10 m/s cruise overspeed vs the stub). Here the FIRST REAL
        # frame is the strobe (see step), so cycle 1 sees true IMU/enc
        # and theta initializes exactly like the stub's first sample.
        ch.run(BOOT_WINDOW_S)
        self._booted = False


    # ---------------- the controller slot ----------------
    def step(self, s: RaceSensorFrame) -> RaceMotorFrame:
        ch = self._ch
        s.task = self._task_word()          # harness frame carries the route
        words = pack_sensors(s)
        for i in range(1, 9):
            ch.write_word(RACE_BASE + 4 * i, words[i])
        ch.run_period()
        if not self._booted:
            # the frame just written WAS the strobe (seq != boot baseline)
            # -> cycle 1 ran on REAL sensors. Guard the heartbeat here;
            # the balance twin checks it in reset() instead because its
            # strobe frame is synthetic.
            ch.wait_heartbeat(
                RACE_BASE + 0x2C,
                "(check race_fw.elf build / RAC2 magic / "
                "task word / UsageFault)")
            self._booted = True

        duty_word = ch.read_word(RACE_BASE + 0x24)
        buzz_led = ch.read_word(RACE_BASE + 0x28)
        fw_seq = ch.read_word(RACE_BASE + 0x2C)
        if fw_seq == self.fw_seq:
            raise RuntimeError(
                f"firmware stuck: fw_seq frozen at {fw_seq} after a "
                f"strobed period (fault words at 0x2001FFB8)")
        m = RaceMotorFrame(
            duty_l=mailbox.lo16(duty_word), duty_r=mailbox.hi16(duty_word),
            buzzer_ms=buzz_led & 0xFFFF, led=(buzz_led >> 16) & 0xFFFF,
            fw_seq=fw_seq,
            status=ch.read_word(RACE_BASE + 0x30),
            t_mission_ms=ch.read_word(RACE_BASE + 0x34),
            e_lat_mm=mailbox.lo16(ch.read_word(RACE_BASE + 0x38)),
            v_plan_mm_s=ch.read_word(RACE_BASE + 0x38) >> 16,
            odo_cm=(mailbox.lo16(ch.read_word(RACE_BASE + 0x3C)),
                    mailbox.hi16(ch.read_word(RACE_BASE + 0x3C))),
        )
        self._absorb_outputs(m)
        self._consumed_line_bits = ch.read_word(RACE_BASE + 0x20) & 0xFF
        return m


# ---- the peripheral path (production, one ELF on both targets) ----

# Same bench as twin's peripheral backend (bot.periph -- the shared
# hardware map both apps' machines drive); the race-specific additions
# are the PF0-7 line-bar pins and the task word.
from bot.periph import (  # noqa: E402 -- shared peripheral bench
    BENCH, BENCH_BATT, BENCH_FI, BENCH_SEQ,
    ENC_PORTS, TIM3_CNT, TIM4_CNT, decode_duty_pair,
    inject_encoder, send_line, write_bench,
)
from bot.line_sensor import ACTIVE_LOW
GPIOF_LINE_HIGH = [f"gpioPortF OnGPIO {i} {'true' if ACTIVE_LOW else 'false'}"
                   for i in range(8)]


class RacePeriphBackend(RaceMissionCore):
    """The production race firmware behind its REAL peripheral path.

    Sensor side: the plant's raw frame goes to the IMU bench (latched by
    the MPU6050 model; the firmware reads it through the I2C driver at
    its own 200 Hz data-ready); wheel angles become quadrature EDGES on
    the encoder timers; line_bits is driven onto the PF0-7 bar pins
    (module active-low: on-tape pulls the pin LOW); battery mV goes
    through the ADC model's bench. Actuator side: duty is decoded from
    TIM1 CCR + the TB6612 direction word -- what the driver drove. The
    task word is mission CONFIGURATION, written into the status window
    pre-boot (retask = cold boot). The RAC2 telemetry mirrors keep the
    grader's contract.

    Encoder timers are the hand model (firmware/enc_model.cs --
    Renode's STM32_Timer throws on the 16-bit wrap, real silicon wraps;
    probes in output/race-integration/), so counts cross 0x10000 with
    true board semantics and the per-period check compares mod 65536.
    Counters preset to 0x8000 (origin convention, twin parity); edges
    spaced with 20 us RunFor ticks.
    """

    name = "fw-periph[race_fw.elf]"

    def __init__(self, task: int = 2, dt: float = 0.005,
                 v_batt: float = 11.1, turbo: bool | None = None,
                 elf_path: str | None = None, renode_path: str | None = None,
                 mips: int = 4, uart_telemetry: bool = False,
                 gdb_port: int | None = None) -> None:
        super().__init__(task, dt, turbo)
        self.v_batt = v_batt          # firmware reads the ADC instead
        self._elf_path = os.path.abspath(elf_path or DEFAULT_ELF)
        self._ch: RenodeChannel | None = None
        self._mips = mips
        self._renode_path = renode_path
        self._uart_telemetry = uart_telemetry
        self.gdb_port = gdb_port
        from collections import deque
        self._debug_rx = deque()
        self._serial_events = deque(maxlen=32)
        self._serial_seq = 0
        self._serial_pending = bytearray()
        self._serial_total = 0
        self._serial_latest = None
        self.tty = None               # TerminalTester on usart2 (see reset)
        self.uart_log = bytearray()   # raw TX bytes, same seam as tty
        self._booted = False
        self._idx = [0, 0]
        self._injected = [0, 0]
        self._line_bits = 0
        self.reset()

    # ---------------- lifecycle ----------------
    def reset(self, x0: float = 0.0, y0: float = 0.0,
              psi0: float = 0.0) -> None:
        """Cold boot: fresh machine; the firmware derives the spawn
        prior from its own route table (identical triple, same as the
        mailbox backend)."""
        del x0, y0, psi0
        if self._ch is not None:
            self._ch.emu.clear()
        else:
            # first construction in this process: the Emulation singleton
            # may still hold another backend's same-named machine, and
            # add_mach would silently return None
            from pyrenode3.wrappers import Emulation
            Emulation().clear()
        self._reset_mission()
        self._idx = [0, 0]
        self._injected = [0, 0]
        self._line_bits = 0
        ch = RenodeChannel(self._elf_path, self.dt, mips=self._mips,
                           mach_name="race", renode_path=self._renode_path)
        self._ch = ch
        self._debug_rx.clear()
        self._debug_reply = None
        self._serial_events.clear()
        self._serial_seq = self._serial_total = 0
        self._serial_pending.clear()
        self._serial_latest = None
        if self._uart_telemetry:
            # attach before the machine's first execution (twin rule: a
            # UART receiver attached after any run crashes Renode's bus);
            # the tester is WRITE-side only -- its waiting reads hang on
            # an empty buffer, assertions go against uart_log
            from pyrenode3.wrappers import TerminalTester
            from System import Action, Byte
            self.uart_log = bytearray()
            uart = ch.mach.sysbus.get_child("usart2")
            uart.add_CharReceived(Action[Byte](
                self._capture_uart))
            self.tty = TerminalTester(uart, 5.0)
        # The monitor calls these same receivers. Cache them to avoid its
        # text parser per edge; AF-mode and pin-map guards still apply.
        self._encoder_inputs = [ch.mach.sysbus.get_child(port).internal
                                for port, _, _ in ENC_PORTS]
        self._line_input = ch.mach.sysbus.get_child("gpioPortF").internal
        ch.preset_counter("timer3", 0x8000)  # initial model state, clocks stay off
        ch.preset_counter("timer4", 0x8000)
        ch.write_word(RACE_BASE + 0x20,
                      self._task_word() << 16)   # the task word slot
        for cmd in GPIOF_LINE_HIGH:        # bar off-tape: module idles HIGH
            ch.mon.execute(cmd)
        self._write_bench(RaceSensorFrame(seq=1))
        # Boot window runs startup + IMU init only. NO strobe: the first
        # REAL frame (in step) is the strobe, so cycle 1 seeds the
        # complementary filter on true IMU -- the mailbox backend's
        # measured rule (+0.10 m/s overspeed otherwise).
        ch.run(BOOT_WINDOW_S)
        self._booted = False
        from .diagnostics import CEstimates
        self._estimates = CEstimates(self._elf_path, read_word=ch.read_word)
        if self.gdb_port is not None:
            if not 1 <= self.gdb_port <= 65535:
                raise ValueError("GDB port must be between 1 and 65535")
            # Explicit false: Renode 1.17's default can auto-start the whole
            # emulation on GDB attach, outside the sensor/plant coupling.
            out, err = ch.mon.execute(f"machine StartGdbServer {self.gdb_port} false")
            if err:
                raise RuntimeError(f"GDB server failed: {out} {err}")

    def diagnostics(self) -> dict:
        return self._estimates.snapshot(self.fw_seq, self.phase)

    def _capture_uart(self, value) -> None:
        value = int(value)
        self._serial_total += 1
        self.uart_log.append(value)
        if len(self.uart_log) > 65536:
            del self.uart_log[:4096]
        if value == 10:
            line = self._serial_pending.decode("ascii", errors="replace").rstrip("\r")
            self._serial_pending.clear()
            if line.startswith("T "):
                self._serial_latest = line
                # The first T after the queued stat terminator is delivered
                # is its reply. Periodic T lines remain a latest-value sample.
                if self._debug_reply == "stat" and not self._debug_rx:
                    self._serial_seq += 1
                    self._serial_events.append({"seq": self._serial_seq,
                                                "text": line, "command": "stat"})
                    self._debug_reply = None
            elif line:
                self._serial_seq += 1
                event = {"seq": self._serial_seq, "text": line}
                if line == "pong" and self._debug_reply == "ping":
                    event["command"] = "ping"
                    self._debug_reply = None
                self._serial_events.append(event)
        elif len(self._serial_pending) < 256:
            self._serial_pending.append(value)

    def serial_diagnostics(self) -> dict:
        return {"enabled": self._uart_telemetry, "rx_pending_bytes": len(self._debug_rx),
                "pending_command": self._debug_reply,
                "tx_total_bytes": self._serial_total, "latest_telemetry": self._serial_latest,
                "events": list(self._serial_events), "last_seq": self._serial_seq,
                "gdb_port": self.gdb_port}

    def queue_debug_command(self, command: str) -> None:
        """Read-only commands, one RX byte per normal coupling; never run the CPU alone."""
        if not self._uart_telemetry:
            raise ValueError("serial capture disabled; launch with --serial-debug")
        if command not in ("ping", "stat"):
            raise ValueError("debug serial commands are ping or stat")
        if self._debug_rx or self._debug_reply:
            raise ValueError("serial command pending")
        self._debug_reply = command
        self._debug_rx.extend((command + "\n").encode("ascii"))

    # ---------------- sensor side ----------------
    def _write_bench(self, s: RaceSensorFrame) -> None:
        write_bench(self._ch, s)

    def _inject_encoder(self, wheel: int, target: int) -> None:
        inject_encoder(self._ch, self._encoder_inputs, self._idx,
                       self._injected, wheel, target)

    def _drive_line(self, line_bits: int) -> None:
        """Put the bar on the PF0-7 pins: module active-low, so an
        on-tape bit drives the pin LOW (the firmware's read inverts)."""
        line_bits &= 0xFF
        if line_bits == self._line_bits:
            return
        changed = line_bits ^ self._line_bits
        for i in range(8):
            if changed >> i & 1:
                low = bool(line_bits >> i & 1) == ACTIVE_LOW
                self._line_input.OnGPIO(i, not low)
        self._line_bits = line_bits

    # ---------------- the controller slot ----------------
    def step(self, s: RaceSensorFrame) -> RaceMotorFrame:
        ch = self._ch
        if self._debug_rx:
            from Antmicro.Renode.Peripherals.UART import IUART
            IUART(ch.mach.sysbus.get_child("usart2").internal).WriteChar(self._debug_rx.popleft())
        self._write_bench(s)
        self._inject_encoder(0, s.enc_l)
        self._inject_encoder(1, s.enc_r)
        self._drive_line(s.line_bits)
        ch.run_period()
        if not self._booted:
            # the frame just written WAS the strobe -> cycle 1 ran on
            # REAL sensors (the mailbox backend's boot rule)
            ch.wait_heartbeat(
                RACE_BASE + 0x2C,
                "(check race_fw.elf build / RAC2 window / "
                "task word / UsageFault)")
            self._booted = True

        duty_l, duty_r = decode_duty_pair(ch.read_word)
        buzzer_word = ch.read_word(RACE_BASE + 0x28)
        fw_seq = ch.read_word(RACE_BASE + 0x2C)
        if fw_seq == self.fw_seq:
            raise RuntimeError(
                f"firmware stuck: fw_seq frozen at {fw_seq} (fault "
                f"words at 0x2001FFB8)")
        m = RaceMotorFrame(
            duty_l=duty_l,
            duty_r=duty_r,
            buzzer_ms=buzzer_word & 0xFFFF,
            led=(buzzer_word >> 16) & 0xFFFF,
            fw_seq=fw_seq,
            status=ch.read_word(RACE_BASE + 0x30),
            t_mission_ms=ch.read_word(RACE_BASE + 0x34),
            e_lat_mm=mailbox.lo16(ch.read_word(RACE_BASE + 0x38)),
            v_plan_mm_s=ch.read_word(RACE_BASE + 0x38) >> 16,
            odo_cm=(mailbox.lo16(ch.read_word(RACE_BASE + 0x3C)),
                    mailbox.hi16(ch.read_word(RACE_BASE + 0x3C))),
        )
        self._absorb_outputs(m)
        self._consumed_line_bits = ch.read_word(RACE_BASE + 0x20) & 0xFF
        return m

    def send_line(self, text: str) -> None:
        send_line(self._ch, text)
