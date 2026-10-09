"""RenodeFirmwareBackend -- the REAL firmware in the Controller slot.

Channel: bot.renode (shared with the race backend). The coupling is
the radar twin's twin_step shape, minus the text channel:

    step():  write the 7 harness-owned sensor words -> RunFor(dt)
             -> read the duty word + fw_seq heartbeat

The firmware (firmware/twin/main.c) polls the mailbox seq strobe, runs the
same LQR/ complementary filter as the Python stub, writes duty + fw_seq.
Nothing here decodes physics -- the mailbox raw frame is all the
firmware ever sees, exactly like the stub.
"""
import os
import time

from bot.backend import Controller
from bot.mailbox import MotorFrame, SensorFrame
from bot.renode import (BOOT_TIMEOUT_WALL_S, BOOT_WINDOW_S,
                        RenodeChannel)   # internal imports
from bot.renode import DEFAULT_PORTABLE   # the documented re-export: tests pin this one

from .mailbox import MAGIC, TWIN_BASE, decode_motor, pack_sensors


class RenodeFirmwareBackend(Controller):
    """Controller impl driving firmware in Renode (name shows in HUD)."""

    name = "fw:balance"

    def __init__(self, elf_path: str, dt: float, renode_path: str | None = None,
                 mips: int = 4) -> None:
        self.elf_path = elf_path
        self.dt = dt
        self.name = f"fw[{os.path.basename(elf_path)}]"
        self.fw_seq = 0            # last heartbeat seen (HUD/live check)
        self._ch: RenodeChannel | None = None
        self._mips = mips
        self._renode_path = renode_path
        self.reset()

    def reset(self) -> None:
        """Full cold boot: fresh machine, then wait for the heartbeat.

        TwinLoop.reset() lands here on startup and on user reset -- a
        machine rebuild (~1 s) buys exact restart semantics, no
        half-reset state to reason about.
        """
        if self._ch is not None:
            self._ch.emu.clear()
        self.fw_seq = 0
        ch = RenodeChannel(self.elf_path, self.dt, mips=self._mips,
                           renode_path=self._renode_path)
        self._ch = ch
        ch.write_word(TWIN_BASE, MAGIC)
        words = pack_sensors(SensorFrame(seq=1))
        for i in range(1, 8):      # seq..enc_r, harness-owned words only
            ch.write_word(TWIN_BASE + 4 * i, words[i])
        # boot the firmware with the frame ALREADY in RAM -- it records
        # the current seq as its baseline and waits for a CHANGE, so the
        # strobe must come after boot, not before (first draft raced it)
        ch.run(BOOT_WINDOW_S)
        ch.write_word(TWIN_BASE + 4, 2)   # the strobe: seq change
        self.fw_seq = ch.wait_heartbeat(
            TWIN_BASE + 0x24,
            "(check firmware build / mailbox magic / UsageFault)")

    def step(self, s: SensorFrame) -> MotorFrame:
        ch = self._ch
        words = pack_sensors(s)
        for i in range(1, 8):      # magic stays from reset; never touch
            ch.write_word(TWIN_BASE + 4 * i, words[i])  # duty/fw_seq
        ch.run_period()
        duty_word = ch.read_word(TWIN_BASE + 0x20)
        fw_seq = ch.read_word(TWIN_BASE + 0x24)
        if fw_seq == self.fw_seq:
            raise RuntimeError(
                f"firmware stuck: fw_seq frozen at {fw_seq} after a "
                f"strobed period (fault words at 0x2001FFB8)")
        self.fw_seq = fw_seq
        return decode_motor(duty_word, fw_seq)


# ---- the peripheral path (production, one ELF on both targets) ----

# the shared bench lives one layer down (twin and race drive the same
# machine through it): hardware map, duty decode, encoder-edge and
# UART-line injection
from bot.periph import (BENCH, BENCH_BATT, BENCH_FI, BENCH_SEQ,  # noqa: E402
                        TIM3_CNT, TIM4_CNT, decode_duty_pair,
                        inject_encoder, send_line, write_bench)


class RenodePeriphBackend(Controller):
    """The production firmware behind its REAL peripheral path.

    Sensor side: the plant's raw frame goes to the IMU bench (the
    Renode MPU6050 model latches it; the firmware reads it through the
    I2C driver at its own 200 Hz data-ready); wheel angles become
    quadrature EDGES injected at the encoder timers' channel inputs;
    battery millivolts go through the ADC model's bench. Actuator side:
    the duty is decoded from TIM1 CCR + the TB6612 direction word --
    what the driver actually drove, never a commanded value.

    TIM3/TIM4 use firmware/enc_model.cs because Renode 1.17's stock
    encoder path throws on wrap/underflow. The replacement wraps at
    16 bits. Counters start at 0x8000 as an origin convention; edges
    keep their 20 us RunFor spacing. Each batch is checked modulo
    65536, and a lost edge is loud.
    """

    name = "fw:balance-periph"

    def __init__(self, elf_path: str, dt: float,
                 renode_path: str | None = None, mips: int = 4,
                 uart_telemetry: bool = False) -> None:
        self.elf_path = elf_path
        self.dt = dt
        self.name = f"fw-periph[{os.path.basename(elf_path)}]"
        self.fw_seq = 0
        self._ch: RenodeChannel | None = None
        self._mips = mips
        self._renode_path = renode_path
        self._uart_telemetry = uart_telemetry
        self.tty = None           # TerminalTester on usart2 (see reset)
        self.uart_log = bytearray()   # raw TX bytes, same seam as tty
        self._idx = [0, 0]         # quadrature state, left/right
        self._injected = [0, 0]    # cumulative counts injected
        self.reset()

    def reset(self) -> None:
        if self._ch is not None:
            self._ch.emu.clear()
        else:
            # first construction in this process: the Emulation singleton
            # may still hold another backend's same-named machine, and
            # add_mach would silently return None
            from pyrenode3.wrappers import Emulation
            Emulation().clear()
        self.fw_seq = 0
        self._idx = [0, 0]
        self._injected = [0, 0]
        ch = RenodeChannel(self.elf_path, self.dt, mips=self._mips,
                           renode_path=self._renode_path)
        self._ch = ch
        if self._uart_telemetry:
            # MUST attach before the machine's first execution: a UART
            # receiver attached after any RunFor crashes Renode's bus
            # with ObjectDisposedException and every later sysbus read
            # dies with it (probed 2026-09-29,
            # output/uart-milestone/). The tester (WriteLine injects
            # command lines) and the raw byte tap both measured harmless
            # to heartbeat pacing (131 cycles in 0.655 s attached).
            from pyrenode3.wrappers import TerminalTester
            from System import Action, Byte
            self.uart_log = bytearray()
            uart = ch.mach.sysbus.get_child("usart2")
            uart.add_CharReceived(Action[Byte](
                lambda b: self.uart_log.append(b)))
            self.tty = TerminalTester(uart, 5.0)
        # Cache the same GPIO receivers the monitor invokes. Native calls
        # avoid text parsing per edge and still pass through AF gating.
        from bot.periph import ENC_PORTS
        self._encoder_inputs = [ch.mach.sysbus.get_child(port).internal
                                for port, _, _ in ENC_PORTS]
        ch.preset_counter("timer3", 0x8000)  # initial model state, clocks stay off
        ch.preset_counter("timer4", 0x8000)
        self._write_bench(SensorFrame(seq=1))
        ch.run(BOOT_WINDOW_S)              # init: I2C identity/config...
        # strobe until the first data-ready is consumed: the init may
        # still be arming INT_ENABLE when the first latch lands, and a
        # latch under an unarmed interrupt is silently dropped by the
        # model (probed 2026-09-29)
        seq = 2
        deadline = time.monotonic() + BOOT_TIMEOUT_WALL_S
        while ch.read_word(TWIN_BASE + 0x24) < 1:
            ch.write_word(BENCH_SEQ, seq & 0xFFFFFFFF)
            seq += 1
            ch.run_period()
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "fw-periph: heartbeat never started (IMU init? "
                    "check the bench magic / fault words 0x2001FFB8)")
        self.fw_seq = ch.read_word(TWIN_BASE + 0x24)

    # ---- sensor side ----
    def _write_bench(self, s: SensorFrame) -> None:
        write_bench(self._ch, s)

    def _inject_encoder(self, wheel: int, target: int) -> None:
        inject_encoder(self._ch, self._encoder_inputs, self._idx,
                       self._injected, wheel, target)

    # ---- actuator side ----
    def step(self, s: SensorFrame) -> MotorFrame:
        ch = self._ch
        self._write_bench(s)
        self._inject_encoder(0, s.enc_l)
        self._inject_encoder(1, s.enc_r)
        ch.run_period()
        duty_l, duty_r = decode_duty_pair(ch.read_word)
        fw_seq = ch.read_word(TWIN_BASE + 0x24)
        if fw_seq == self.fw_seq:
            raise RuntimeError(
                f"firmware stuck: fw_seq frozen at {fw_seq} (fault "
                f"words at 0x2001FFB8)")
        self.fw_seq = fw_seq
        return MotorFrame(duty_l=duty_l, duty_r=duty_r, fw_seq=fw_seq)

    def send_line(self, text: str) -> None:
        send_line(self._ch, text)
