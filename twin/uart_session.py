"""The hands-on serial-link session: firmware in Renode + a TCP socket
playing the Bluetooth module's far end.

    .venv/Scripts/python.exe -m twin.uart_session [--elf ...] [--port 4545] [--gdb 3333]
    telnet localhost 4545            # you are now the wireless module
    --elf firmware/twin/balance_fw.elf --bench-imu   # the PRODUCTION ELF,
        # fed a stationary at-trim IMU frame: live "T <seq> <duty> <batt>
        # <ang_mdeg>" telemetry + starved/resume events over telnet

Why not `sysbus.uart CreateTcpServerTerminal 4545` + `machine EnableGDB`
(the textbook commands): THIS Renode (1.17.0 portable) has neither -- the
UART exposes no terminal-creation command at all and the GDB entry is
`machine StartGdbServer` (probed 2026-09-29, output/uart-milestone/
usart2-introspect.log). The bridge instead uses the pyrenode3 objects
the CI gate already uses: the UART's CharReceived event carries each
byte the firmware transmits (it fires on Renode's CPU thread, so the
delegate only queues -- a send() there would propagate a socket error
straight into the emulation and kill it), tt.WriteLine injects each
completed socket line as received characters (the only tester path that
reaches the model's RXNE), and --gdb calls Machine.StartGdbServer --
the same GDB server a full Renode exposes.

The emulation steps in 5 ms quanta; both directions are serviced
between quanta, so round-trip latency is bounded by one quantum.
"""
import argparse
import os
import socket
import sys
import threading
from collections import deque


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ap.add_argument("--elf", default=os.path.join(repo, "firmware",
                                                  "uart_bringup.elf"))
    ap.add_argument("--port", type=int, default=4545,
                    help="TCP port the wireless module's far end listens on")
    ap.add_argument("--gdb", type=int, default=0,
                    help="also start the GDB server on this port "
                         "(arm-none-eabi-gdb -ex 'target remote :PORT')")
    ap.add_argument("--bench-imu", action="store_true",
                    help="feed the bench a stationary AT-TRIM IMU frame "
                         "every quantum so the balance ELF keeps cycling "
                         "(telemetry flows, duty stays near 0; without it "
                         "the firmware starves and the link goes quiet)")
    ap.add_argument("--mips", type=int, default=4)
    args = ap.parse_args()

    from bot.renode import RenodeChannel
    ch = RenodeChannel(args.elf, 0.005, mips=args.mips)

    bench_seq = 0
    if args.bench_imu:
        # the same rest frame the plant produces at the trim keyframe:
        # +1 g up-Z at the trim lean (test_imu_static_frame_at_trim). A
        # ZERO frame would read as 16.7 deg off the law's reference and
        # rail the duty to the traction cap -- measured -450 permille.
        import math
        from bot import mjcf, sensors
        from .renode_backend import BENCH, BENCH_MAGIC
        trim = mjcf.hover_trim_rad()
        lsb = sensors.ACCEL_LSB_PER_G
        frame = (0, int(math.sin(trim) * lsb), int(math.cos(trim) * lsb),
                 0, 0, 0, 0)             # ax ay az gx gy gz temp
        w = ch.write_word
        w(BENCH, BENCH_MAGIC)
        for off, v in zip((0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20),
                          frame):
            w(BENCH + off, v & 0xFFFFFFFF)
        w(BENCH + 0x24, 0)               # FI: no freeze, no whoami override
        w(BENCH + 0x28, 11100)           # 3S nominal

    if args.gdb:
        ch.mach.StartGdbServer(args.gdb, False, "cpu")
        print(f"gdb   : arm-none-eabi-gdb -ex 'target remote :{args.gdb}' "
              f"-ex 'file {args.elf}'")

    # -- the TCP far end: one client, like the paired module --
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(1)
    print(f"serial: telnet localhost {args.port} "
          f"(waiting for the far end to connect...)", flush=True)
    client, _ = srv.accept()
    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print("serial: far end connected -- bridging", flush=True)

    from pyrenode3.wrappers import TerminalTester
    from System import Action, Byte
    uart = ch.mach.sysbus.get_child("usart2")
    tt = TerminalTester(uart, 5.0)

    # TX (firmware -> socket): the event fires on Renode's CPU thread;
    # the delegate must not raise, so it only queues bytes
    tx = deque()

    def on_tx(b):
        tx.append(b)

    uart.add_CharReceived(Action[Byte](on_tx))

    # RX (socket -> firmware): the pump thread accumulates raw bytes; the
    # main loop injects COMPLETE LINES via tt.WriteLine -- the tester's
    # line API is the path that actually reaches the model's RXNE (its
    # per-byte WriteChar only feeds the tester's own matcher, probed
    # 2026-09-29); the firmware terminates lines on \n or \r alike
    rx = bytearray()
    threading.Thread(target=_pump_rx, args=(client, rx), daemon=True).start()

    try:
        while True:
            if args.bench_imu:           # the data-ready latch, LAST
                bench_seq += 1
                ch.write_word(BENCH + 0x04, bench_seq & 0xFFFFFFFF)
            ch.run(0.005)
            while b"\n" in rx:
                line, _, rest = bytes(rx).partition(b"\n")
                rx.clear()
                rx.extend(rest)
                tt.WriteLine(line.decode("utf-8", errors="replace")
                             .rstrip("\r"))
            if tx:
                out = bytes(tx)
                tx.clear()
                client.sendall(out)     # far end gone -> clean shutdown
    except (BrokenPipeError, ConnectionError, OSError):
        print("serial: far end disconnected -- session over")
    finally:
        client.close()
        srv.close()
    return 0


def _pump_rx(client: socket.socket, rx: bytearray) -> None:
    while True:
        try:
            data = client.recv(4096)
        except ConnectionError:
            os._exit(0)              # link died: main loop exits too
        if not data:
            os._exit(0)              # far end hung up: session over
        rx.extend(data)


if __name__ == "__main__":
    sys.exit(main())
