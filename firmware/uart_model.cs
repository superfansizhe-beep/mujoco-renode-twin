// UART wire slice for USART2: baud-paced frames and overrun, on top of
// Renode 1.17's stock STM32_UART (which stores SR/BRR/CR1, moves bytes
// both ways, and paces nothing). The driver's per-byte deadlines
// (firmware/stm32f4_uart.h, ~87 us at 115200) assume this wire:
//
//   - a frame occupies the line for 1 start + data (CR1.M) + parity
//     (CR1.PCE) + 1 stop bit at the BRR-derived baud of the pinned
//     16 MHz PCLK1 HSI tree (RM0090 rev 22, ch. 30: USARTDIV/BRR baud
//     generation, SR.TXE/TC/RXNE/ORE semantics). A frame inherits the
//     BRR/CR1 in effect when it starts.
//   - TX: bytes queue and leave one frame apart; the character reaches
//     the CharReceived taps when its frame completes. TXE reads low
//     while a frame is queued or on the wire (single-buffer strictness
//     -- silicon's double buffer lets TXE lead by one byte, so this
//     side is conservative), TC reads low until the last frame ends.
//   - RX: injected bytes deliver after their frame time; one that
//     completes over an unread RXNE is lost and latches ORE, cleared by
//     the SR-read-then-DR-read sequence. Bus disable (RCC) or a cleared
//     CR1.RE drops injected input.
//
// Frame timing rides two private repl-attached STM32_Timers (uartTxBaud
// / uartRxBaud, one per direction -- full duplex), armed per frame at
// the timers' exact clock-entry rate (the same mechanism whose 16 MHz
// precision the RCC gates pin to +-2 ticks/ms). Two Renode 1.17
// scheduling traps probed on the way (output/uart-wire/):
// machine.ScheduleAction never fires a closure lambda (the iwdg_model
// trap), and a this-bound method group DOES fire -- but with
// millisecond-scale slop, useless for 87 us frames.
//
// Not modeled: DMA, IrDA/smartcard/LIN, flow control, framing/parity
// error flags, BREAK, oversampling detail beyond OVER8's divisor, and
// a mid-frame RCC clock kill (the byte in flight is dropped, not
// frozen mid-wire).
// Loaded at runtime by bot/renode.py; attached by stm32f407zg.repl as
//     usart2: UART.UARTWireSim @ sysbus <0x40004400, +0x100>
//         txBaud: uartTxBaud
//         rxBaud: uartRxBaud
using System;
using System.Collections.Generic;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Peripherals.UART;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.UART
{
    // WriteChar is a plain (interface-implementing) method on the stock
    // model -- not virtual -- so the subclass re-lists IUART to rebind it
    // to the paced path; the register accesses are true virtuals.
    public class UARTWireSim : STM32_UART, IUART
    {
        public UARTWireSim(IMachine machine, STM32_Timer txBaud,
                           STM32_Timer rxBaud) : base(machine)
        {
            this.machine = machine;
            this.txBaud = txBaud;
            this.rxBaud = rxBaud;
            txBaud.LimitReached += TxFire;
            rxBaud.LimitReached += RxFire;
        }

        public override uint ReadDoubleWord(long offset)
        {
            if(offset == RegSR)
            {
                srWasRead = true;
                var sr = base.ReadDoubleWord(offset);
                if(txPumping || txQueue.Count > 0)
                {
                    sr &= ~(SR_TXE | SR_TC);   // a frame is on the wire
                }
                if(ore)
                {
                    sr |= SR_ORE;
                }
                return sr;
            }
            if(offset == RegDR)
            {
                var v = base.ReadDoubleWord(offset);
                if(srWasRead)
                {
                    ore = false;        // the SR-then-DR read clears ORE
                    srWasRead = false;
                }
                return v;
            }
            return base.ReadDoubleWord(offset);
        }

        public override void WriteDoubleWord(long offset, uint value)
        {
            if(offset == RegDR)
            {
                txQueued++;
                txQueue.Enqueue((byte)value);
                if(!txPumping)
                {
                    PumpTx();
                }
                return;
            }
            base.WriteDoubleWord(offset, value);
        }

        public new void WriteChar(byte value)
        {
            if(!machine.SystemBus.IsPeripheralEnabled(this)
               || (base.ReadDoubleWord(RegCR1) & CR1_RE) == 0)
            {
                return;                 // clock off / receiver off: lost
            }
            rxInjected++;
            rxQueue.Enqueue(value);
            if(!rxPumping)
            {
                PumpRx();
            }
        }

        public override void Reset()
        {
            base.Reset();
            generation++;               // in-flight frames die with it
            txQueue.Clear();
            rxQueue.Clear();
            txPumping = false;
            rxPumping = false;
            ore = false;
            srWasRead = false;
            txBaud.Enabled = false;
            rxBaud.Enabled = false;
        }

        // ---- harness-visible state (probe/tests read via the machine) ----
        public long TxQueued { get { return txQueued; } }
        public long RxInjected { get { return rxInjected; } }
        public long TxDelivered { get { return txDelivered; } }
        public long RxDelivered { get { return rxDelivered; } }

        private void PumpTx()
        {
            if(txQueue.Count == 0)
            {
                txPumping = false;
                return;
            }
            txPumping = true;
            txByte = txQueue.Dequeue();
            txGen = generation;
            Arm(txBaud, FrameTicks());
        }

        private void TxFire()
        {
            if(txGen == generation
               && machine.SystemBus.IsPeripheralEnabled(this)
               && (base.ReadDoubleWord(RegCR1) & CR1_TE) != 0)
            {
                txDelivered++;
                base.WriteDoubleWord(RegDR, txByte);  // stock emits the char
            }
            PumpTx();
        }

        private void PumpRx()
        {
            if(rxQueue.Count == 0)
            {
                rxPumping = false;
                return;
            }
            rxPumping = true;
            rxByte = rxQueue.Dequeue();
            rxGen = generation;
            Arm(rxBaud, FrameTicks());
        }

        private void RxFire()
        {
            if(rxGen == generation
               && machine.SystemBus.IsPeripheralEnabled(this))
            {
                if((base.ReadDoubleWord(RegSR) & SR_RXNE) != 0)
                {
                    ore = true;         // overrun: the byte is lost
                }
                else
                {
                    rxDelivered++;
                    base.WriteChar(rxByte);
                }
            }
            PumpRx();
        }

        private void Arm(STM32_Timer t, ulong ticks)
        {
            t.EventEnabled = true;      // survives nothing else touching it
            t.Value = 0;
            t.Limit = Math.Max(ticks, 1);
            t.Mode = WorkMode.OneShot;
            t.Enabled = true;
        }

        private ulong FrameTicks()
        {
            var cr1 = base.ReadDoubleWord(RegCR1);
            var brr = base.ReadDoubleWord(RegBRR) & 0xFFFF;
            var over8 = (cr1 & CR1_OVER8) != 0;
            // USARTDIV is fixed-point: mantissa BRR[15:4], fraction
            // BRR[3:0]/16 (BRR[2:0]/8 with OVER8) -- 139 is 8.6875,
            // not a divisor of 139 (RM0090 ch. 30 USARTDIV/BRR table)
            var usartdiv = (brr >> 4)
                + (over8 ? (brr & 0x7) / 8.0 : (brr & 0xF) / 16.0);
            var baud = PCLK1 / ((over8 ? 8.0 : 16.0) * Math.Max(usartdiv, 1.0));
            var bits = 1                                  // start
                     + ((cr1 & CR1_M) != 0 ? 9 : 8)       // data
                     + ((cr1 & CR1_PCE) != 0 ? 1 : 0)     // parity
                     + 1;                                 // stop
            return (ulong)Math.Round(WireHz * bits / baud);
        }

        // the repl pins APB1 and the baud timers to the 16 MHz HSI tree
        private const double PCLK1 = 16000000.0;
        private const double WireHz = 16000000.0;
        private const long RegSR = 0x00;
        private const long RegDR = 0x04;
        private const long RegBRR = 0x08;
        private const long RegCR1 = 0x0C;
        private const uint SR_TXE = 1u << 7;
        private const uint SR_TC = 1u << 6;
        private const uint SR_RXNE = 1u << 5;
        private const uint SR_ORE = 1u << 3;
        private const uint CR1_OVER8 = 1u << 15;
        private const uint CR1_M = 1u << 12;
        private const uint CR1_PCE = 1u << 10;
        private const uint CR1_TE = 1u << 3;
        private const uint CR1_RE = 1u << 2;

        private readonly IMachine machine;
        private readonly STM32_Timer txBaud;
        private readonly STM32_Timer rxBaud;
        private readonly Queue<byte> txQueue = new Queue<byte>();
        private readonly Queue<byte> rxQueue = new Queue<byte>();
        private bool txPumping;
        private bool rxPumping;
        private byte txByte;
        private byte rxByte;
        private int txGen;
        private int rxGen;
        private bool ore;
        private bool srWasRead;
        private int generation;
        private long txQueued;
        private long rxInjected;
        private long txDelivered;
        private long rxDelivered;
    }
}
