"""The UART bring-up gate: firmware/uart_bringup.elf talks the Bluetooth
link line protocol through the REAL USART2 driver
(firmware/stm32f4_uart.c) against the built-in UART.STM32_UART.

The "wireless other end" in CI is pyrenode3's TerminalTester attached to
usart2 -- WriteLine injects the bytes a Bluetooth module would deliver,
NextLine consumes what the firmware transmitted (the same tester that
backs Renode's own UART tests). The interactive TCP-terminal flavor of
the same bridge is verified by output/uart-milestone/ probes and
documented in firmware/uart_status.md.
"""
import os
import re
import socket
import unittest

REPO = os.path.join(os.path.dirname(__file__), "..")
FW = os.path.join(REPO, "firmware")
UART_ELF = os.path.join(FW, "uart_bringup.elf")

RES = 0x2001FA00
RESULT_MAGIC = 0x54524155          # "UART" little-endian
FAULT_MAGIC_ADDR = 0x2001FFB8      # fault words sit above every carve

USART2 = 0x40004400
GPIOA = 0x40020000
RCC = 0x40023800


def _renode_ready():
    from bot.renode import DEFAULT_PORTABLE
    os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)
    try:
        import pyrenode3  # noqa: F401
    except Exception as exc:
        return None, f"pyrenode3 not importable ({exc.__class__.__name__}: {exc})"
    if not DEFAULT_PORTABLE or not os.path.isdir(DEFAULT_PORTABLE):
        return None, ("Renode portable not configured "
                      f"(set RENODE_PORTABLE): {DEFAULT_PORTABLE}")
    if not os.path.isfile(UART_ELF):
        return None, f"{UART_ELF} missing -- bash firmware/build_uart.sh"
    return True, ""


class TestUARTLayout(unittest.TestCase):
    """Static: the carve bounds and the baud/bitness constants."""

    def test_results_block_clears_the_imu_trace_and_fault_words(self):
        imu = open(os.path.join(FW, "imu_bringup.h")).read()
        trace_base = int(re.search(r"#define\s+IMU_TRACE_BASE\s+(0x[0-9A-Fa-f]+)",
                                   imu).group(1), 16)
        cap = int(re.search(r"#define\s+IMU_TRACE_CAP\s+(\d+)u?", imu).group(1))
        trace_end = trace_base + 8 + 4 * cap      # 2-word header + u32 entries
        uart = open(os.path.join(FW, "uart_bringup.h")).read()
        base = int(re.search(r"#define\s+UART_RESULT_BASE\s+(0x[0-9A-Fa-f]+)",
                             uart).group(1), 16)
        self.assertGreater(base, trace_end,
                           "the uart block must sit above the imu trace")
        self.assertLessEqual(base + 0x18, FAULT_MAGIC_ADDR,
                             "the uart block must stay below the fault words")

    def test_brr_matches_the_documented_baud(self):
        drv = open(os.path.join(FW, "stm32f4_uart.h")).read()
        brr = int(re.search(r"#define\s+UART2_BRR\s+(\d+)u", drv).group(1))
        baud = int(re.search(r"#define\s+UART2_BAUDRATE\s+(\d+)u", drv).group(1))
        div = 16000000 / (16 * baud)              # PCLK1 = 16 MHz HSI tree
        m, f = int(div), round((div - int(div)) * 16)
        if f == 16:
            m, f = m + 1, 0
        self.assertEqual(brr, (m << 4) | f,
                         "BRR must track UART2_BAUDRATE at the 16 MHz tree")

    def test_driver_enables_tx_and_rx_together(self):
        """RE gates the receiver on silicon; the gate pins the register
        readback in sim, this pins the source keeps writing all three."""
        src = open(os.path.join(FW, "stm32f4_uart.c")).read()
        self.assertRegex(
            src, r"USART_CR1\)\s*=\s*CR1_UE\s*\|\s*CR1_TE\s*\|\s*CR1_RE",
            "uart2_init must set UE|TE|RE together")


class TestUARTBringup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()    # singleton: outlive any earlier machine
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(UART_ELF, 0.005)
        self.sb = self._ch.sysbus
        uart = self._ch.mach.sysbus.get_child("usart2")
        from pyrenode3.wrappers import TerminalTester
        from Antmicro.Renode.Time import TimeInterval
        self.TI = TimeInterval
        self.tt = TerminalTester(uart, 5.0)
        self._ch.run(0.05)     # boot: init + banner

    def tearDown(self):
        self._ch.emu.clear()

    def _res(self, i):
        return int(self.sb.ReadDoubleWord(RES + 4 * i))

    def _next(self):
        line = self.tt.NextLine(self.TI.FromSeconds(2.0), True)
        self.assertIsNotNone(line, "firmware sent no more lines")
        return line.Line

    # ---- the gates ----
    def test_config_contract_is_written_at_runtime(self):
        self.assertEqual(self.sb.ReadDoubleWord(RCC + 0x40) & 0x20000,
                         0x20000, "APB1ENR.USART2EN")
        self.assertEqual(self.sb.ReadDoubleWord(RCC + 0x30) & 0x1, 0x1,
                         "AHB1ENR.GPIOAEN")
        moder = self.sb.ReadDoubleWord(GPIOA)
        self.assertEqual((moder >> 4) & 0xF, 0xA, "PA2/PA3 AF mode (10)")
        self.assertEqual((self.sb.ReadDoubleWord(GPIOA + 0x08) >> 4) & 0xF,
                         0xF, "PA2/PA3 high speed")
        self.assertEqual((self.sb.ReadDoubleWord(GPIOA + 0x0C) >> 4) & 0xF,
                         0x4, "PA3 pull-up (01), PA3 floating TX (00)")
        self.assertEqual((self.sb.ReadDoubleWord(GPIOA + 0x20) >> 8) & 0xFF,
                         0x77, "AFRL: AF7 on PA2/PA3")
        self.assertEqual(self.sb.ReadDoubleWord(USART2 + 0x08), 139,
                         "BRR 0x8B = 115200 at 16 MHz")
        self.assertEqual(self.sb.ReadDoubleWord(USART2 + 0x0C), 0x200C,
                         "CR1 = UE|TE|RE (the model stores all three; the "
                         "probe-1 'RE dropped' note was a mis-written "
                         "0x200A pattern, corrected 2026-09-29)")

    def test_banner_then_periodic_telemetry(self):
        self.assertEqual(self._next(), "UART-UP 115200 8N1")
        self.assertEqual(self._res(0), RESULT_MAGIC, "UART magic")
        self.assertEqual(self._res(1), len("UART-UP 115200 8N1\n"),
                         "banner bytes counted")
        self._ch.run(0.25)                       # 2+ idle telemetry periods
        lines = [self._next(), self._next()]
        for i, line in enumerate(lines):
            self.assertRegex(line, rf"^tick {i + 1}$",
                             "telemetry cadence 100 ms, in order")
        self.assertGreaterEqual(self._res(4), 2, "ticks counted")

    def test_ping_pong_round_trip_through_the_driver(self):
        self._next()                             # banner
        rx0, tx0 = self._res(2), self._res(1)
        self.tt.WriteLine("ping")
        self._ch.run(0.01)
        self.assertEqual(self._next(), "pong")
        self.assertEqual(self._res(2) - rx0, 5, "rx bytes: ping\\n")
        self.assertEqual(self._res(1) - tx0, 5, "tx bytes: pong\\n")
        self.assertEqual(self._res(3), 1, "one dispatched command")
        self.assertEqual(self._res(5), 0x676E6970, "last tag = \"ping\"")

    def test_stat_cross_checks_the_result_words(self):
        self._next()                             # banner
        self.tt.WriteLine("stat")
        self._ch.run(0.01)
        line = self._next()
        m = re.fullmatch(r"tx=(\d+) rx=(\d+) cmds=(\d+) ticks=(\d+)", line)
        self.assertIsNotNone(m, f"stat line shape: {line!r}")
        self.assertEqual(int(m.group(3)), self._res(3), "cmds agree")
        self.assertEqual(int(m.group(4)), self._res(4), "ticks agree")
        self.assertEqual(int(m.group(2)), self._res(2),
                         "rx agrees (nothing arrived since)")
        self.assertEqual(self._res(1) - int(m.group(1)), len(line) + 1,
                         "tx grew by exactly the stat line's own bytes")

    def test_unknown_command_answers_err(self):
        self._next()                             # banner
        self.tt.WriteLine("nope")
        self._ch.run(0.01)
        self.assertEqual(self._next(), "err")
        self.assertEqual(self._res(3), 1, "dispatched (and rejected)")

    def test_gdb_server_opens_the_st_link_equivalent_port(self):
        """The in-process monitor lacks `machine EnableGDB` (probe
        2026-09-29), but Machine.StartGdbServer is reachable directly --
        same GDB server the interactive session exposes. Cluster "cpu" is
        the repl's CPU name."""
        self._ch.mach.StartGdbServer(3355, False, "cpu")
        with socket.create_connection(("127.0.0.1", 3355), timeout=3) as s:
            self.assertTrue(s.getpeername()[0] in ("127.0.0.1", "::1"))
        self._ch.mach.StopGdbServer(3355)


class TestUARTWire(unittest.TestCase):
    """Wire-time gates (RM0090 ch. 30): a round trip pays both
    directions' frames at the configured baud (~87 us each at 115200
    8N1). At a misconfigured slow baud the interactive path degrades
    past timing -- the firmware's own tick transmission blocks RX
    polling and single-DR bytes overrun -- so the BRR-vs-frame contract
    is pinned separately in TestUARTOverrun. The bring-up ELF supplies
    the normal polled driver; TIM2 is the 1 MHz deadline clock
    (16 MHz / (PSC + 1))."""

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(UART_ELF, 0.005)
        self.sb = self._ch.sysbus
        from System import Action, Byte
        from Antmicro.Renode.Peripherals.UART import IUART
        self.uart_log = bytearray()
        uart = self._ch.mach.sysbus.get_child("usart2")
        uart.add_CharReceived(Action[Byte](
            lambda b: self.uart_log.append(b)))
        self.uart = IUART(uart.internal)
        self._ch.run(0.05)     # boot: init + banner on the wire

    def tearDown(self):
        self._ch.emu.clear()

    def _cnt_us(self):
        psc = self.sb.ReadDoubleWord(0x40000028)
        return (self.sb.ReadDoubleWord(0x40000024) * (psc + 1)) / 16.0

    def _round_trip_us(self):
        """Inject "ping\\n", advance until the pong line is complete,
        return the elapsed virtual microseconds (None if it never came)."""
        before = len(self.uart_log)
        t0 = self._cnt_us()
        for b in b"ping\n":
            self.uart.WriteChar(b)
        for _ in range(400):
            self._ch.run(0.0005)
            if self.uart_log.find(b"pong\n", before) != -1:
                return self._cnt_us() - t0
        return None

    def test_round_trip_pays_the_wire_time(self):
        elapsed = self._round_trip_us()
        self.assertIsNotNone(elapsed, "no pong came back")
        self.assertGreaterEqual(
            elapsed, 800,
            "10 frames at 115200 8N1 cost ~868 us -- an instant wire "
            "means the model still paces nothing")
        self.assertLess(elapsed, 20000, "the round trip must stay prompt")


class TestUARTOverrun(unittest.TestCase):
    """Low-level wire gates (CPU self-branches, no firmware noise):
    overrun per RM0090 SR.ORE -- a byte whose frame completes while RXNE
    is still set is lost and latches ORE, cleared by the
    SR-read-then-DR-read sequence -- and the BRR-vs-frame-duration
    contract: a frame occupies the line for its full bit time at the
    baud the fixed-point BRR encodes, so a wrong BRR changes the wire."""

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)
        from pyrenode3.wrappers import Emulation
        Emulation().clear()
        from bot.renode import RenodeChannel
        cls.ch = RenodeChannel(UART_ELF, .005)
        # the tap must exist before the machine's first execution
        # (the post-run attach crashes Renode, see renode_backend.py)
        from System import Action, Byte
        cls.tap = bytearray()
        cls.ch.mach.sysbus.get_child("usart2").add_CharReceived(
            Action[Byte](lambda b: cls.tap.append(b)))

    @classmethod
    def tearDownClass(cls):
        cls.ch.emu.clear()

    def setUp(self):
        from Antmicro.Renode.Peripherals.UART import IUART
        self.ch.mach.internal.Reset()
        self.ch.write_word(0x20010000, 0xE7FEE7FE)
        self.ch.mon.execute('cpu PC 0x20010000')
        self.uart = IUART(self.ch.mach.sysbus.get_child('usart2').internal)
        self.ch.write_word(0x40023840, (1 << 17) | 1)     # USART2 + TIM2
        self.ch.write_word(0x40000028, 15)                # TIM2 PSC: 1 MHz
        self.ch.write_word(0x40000000, 1)                 # TIM2 CEN
        self.ch.write_word(USART2 + 0x08, 139)            # 115200 8N1
        self.ch.write_word(USART2 + 0x0C, 0x200C)         # UE, TE, RE

    def _tx_frame_us(self, char):
        """Write one byte to DR; return the virtual us until the tap
        sees it (the frame's wire time), via TIM2 at 1 MHz."""
        psc = self.ch.read_word(0x40000028) & 0xFFFF
        mark = len(self.tap)
        t0 = self.ch.read_word(0x40000024)
        self.ch.write_word(USART2 + 4, char)
        for _ in range(2000):                    # 2000 x 10us = 20 ms cap
            self.ch.run(.00001)
            if len(self.tap) > mark:
                return (self.ch.read_word(0x40000024) - t0) * (psc + 1) / 16.0
        return None

    def test_wrong_brr_stretches_the_wire(self):
        """The frame duration must follow the fixed-point BRR: 139 is
        8.6875 (~115.1 kBd, ~87 us a frame), 1667 is 104.1875 (~9.6 kBd,
        ~1.04 ms) -- a wrong BRR must change the wire, not pass as
        silent luck."""
        fast = self._tx_frame_us(ord("A"))
        self.assertIsNotNone(fast, "no frame at BRR 139")
        self.assertLessEqual(fast, 300, "115200 8N1 frame is ~87 us")
        self.ch.write_word(USART2 + 0x08, 1667)     # ~9603 baud
        try:
            slow = self._tx_frame_us(ord("B"))
            self.assertIsNotNone(slow, "no frame at BRR 1667")
            self.assertGreaterEqual(
                slow, 800, "~9.6 kBd frame is ~1.04 ms")
            self.assertGreater(slow, 5 * fast,
                               "the wire time must track the BRR")
        finally:
            self.ch.write_word(USART2 + 0x08, 139)

    def test_overrun_drops_the_byte_and_latches_ore(self):
        sr = USART2
        self.uart.WriteChar(65)
        self.ch.run(.0005)
        # RXNE only -- reading DR would consume the byte and void the
        # overrun the next two frames must hit
        self.assertEqual(self.ch.read_word(sr) & 0x20, 0x20, "RXNE set")
        # two bytes complete over the unread one: both lost, ORE latched
        self.uart.WriteChar(66)
        self.uart.WriteChar(67)
        self.ch.run(.0005)
        self.assertEqual(self.ch.read_word(sr) & 0x8, 0x8, "ORE latched")
        self.assertEqual(self.ch.read_word(sr) & 0x20, 0x20,
                         "RXNE still holds the OLDEST byte")
        self.assertEqual(self.ch.read_word(sr + 4), 65,
                         "the overrun byte is lost, not appended")
        # SR-read-then-DR-read clears ORE, like the flag latch
        self.ch.read_word(sr)
        self.ch.read_word(sr + 4)
        self.assertEqual(self.ch.read_word(sr) & 0x8, 0, "ORE cleared")
        # reception resumes once the data register is drained
        self.uart.WriteChar(68)
        self.ch.run(.0005)
        self.assertEqual(self.ch.read_word(sr + 4), 68)


if __name__ == "__main__":
    unittest.main()
