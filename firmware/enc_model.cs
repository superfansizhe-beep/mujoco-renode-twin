// Renode device model: the encoder-timer slice of TIM3/TIM4 (0x40000400
// / 0x40000800), counterpart of the firmware driver
// (firmware/stm32f4_encoder.c).
//
// Why a hand model: Renode 1.17's Timers.STM32_Timer in encoder mode
// THROWS (LimitTimer.set_Value: "Value cannot be larger than limit")
// when edge-driven counting crosses 0x10000 -- real F4 silicon simply
// wraps the 16-bit CNT. The monitor's `Limit` property reaches the
// timer's main counter, not the object the encoder path increments, and
// a reflection shim widening every LimitTimer reachable from the
// peripheral (61 per timer) plus a machine-wide fingerprint scan (2474
// nodes) found no LimitTimer carrying the encoder count at all -- the
// counting value is not field-reachable (probes:
// output/race-integration/limit-count-probe.log, output/enc16_probe*.log).
// Same situation as the F4 ADC (no usable model in Renode's library):
// this file models the slice the driver actually uses.
//
// What it models: x4 quadrature decoding on GPIO inputs 0/1 (A=TI1,
// B=TI2; +1/-1 per state transition, ring (0,0)->(1,0)->(1,1)->(0,1)
// = forward), a 16-bit CNT with TRUE silicon wrap, CNT write access
// (pre-boot origin presets, bench presets), and the driver's register
// block (CR1/SMCR/CCMR1/CCER/PSC/ARR accepted and stored, so
// encoder_init's contract reads back). What it deliberately does NOT
// model: interrupts (both firmwares poll CNT; the nvic lines are gone
// from the repl), clocked/PWM/capture modes, input filters/polarity,
// prescaling, or SMS modes other than x4 mode 011. Counting requires
// the driver's configuration (PSC=0, ARR=0xFFFF, CCMR1=0x101,
// noninverted inputs) and CEN=1; other configurations do not count.
//
// The harness injects wheel motion with the same monitor actions as
// before (`timer3 OnGPIO 0 true` etc.) and verifies CNT mod 65536 every
// coupling period; the firmware's delta16 now sees the same wrap the
// board's silicon performs -- the wrap gate that used to be board-only
// runs in sim (tests/test_firmware_encoder.py).
//
// Loaded at runtime by bot/renode.py (`include "<this file>"`) and
// mapped by firmware/stm32f407zg.repl as:
//     timer3: Timers.EncoderCounterSim @ sysbus <0x40000400, +0x400>
//     timer4: Timers.EncoderCounterSim @ sysbus <0x40000800, +0x400>
using System;
using System.Collections.Generic;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.Timers
{
    // INumberedGPIOOutput exists for the repl's AF table (timer3:
    // 0 -> gpioPortC#06@02 ...): the four channel outputs are wired but
    // never fire -- encoder mode counts input edges, it drives no pins
    public class EncoderCounterSim : IDoubleWordPeripheral, IGPIOReceiver, INumberedGPIOOutput
    {
        public EncoderCounterSim(IMachine machine)
        {
            this.machine = machine;
            regs = new uint[RegSpace / 4];
            var outputs = new Dictionary<int, IGPIO>();
            for(var i = 0; i < 4; i++)
            {
                outputs[i] = new GPIO();
            }
            Connections = outputs;
            Reset();
        }

        public IReadOnlyDictionary<int, IGPIO> Connections { get; private set; }

        public void Reset()
        {
            Array.Clear(regs, 0, regs.Length);
            Array.Clear(pins, 0, pins.Length);
            count = 0;
            idx = 0;          // quadrature ring state (0,0)
        }

        public uint ReadDoubleWord(long offset)
        {
            if(offset == RegCNT)
            {
                return count;
            }
            return regs[offset / 4];
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset == RegCNT)
            {
                count = value & 0xFFFF;   // whole-counter write, like silicon
                return;
            }
            regs[offset / 4] = value;
        }

        public void OnGPIO(int number, bool value)
        {
            if((number != 0 && number != 1) || pins[number] == value)
            {
                return;                   // only A/B edges, no double-fire
            }
            pins[number] = value;
            var newIdx = Idx(pins[0], pins[1]);
            var transition = (newIdx - idx + 4) % 4;
            idx = newIdx;
            if(!machine.SystemBus.IsPeripheralEnabled(this)
                || (regs[RegCR1 / 4] & 1) == 0
                || (regs[RegSMCR / 4] & 7) != 3
                || (regs[RegCCMR1 / 4] & 0xFFFF) != 0x101
                || (regs[RegCCER / 4] & 0xAA) != 0
                || (regs[RegPSC / 4] & 0xFFFF) != 0
                || (regs[RegARR / 4] & 0xFFFF) != 0xFFFF)
            {
                return;
            }
            if(transition == 1)
            {
                count = (count + 1) & 0xFFFF;
                regs[RegCR1 / 4] &= ~0x10u;   // DIR: up
            }
            else if(transition == 3)
            {
                count = (count + 0xFFFF) & 0xFFFF;
                regs[RegCR1 / 4] |= 0x10u;    // DIR: down
            }
        }

        private static int Idx(bool a, bool b)
        {
            // ring order (0,0)=0 -> (1,0)=1 -> (1,1)=2 -> (0,1)=3 -> wrap
            if(!a && !b)
            {
                return 0;
            }
            if(a && !b)
            {
                return 1;
            }
            if(a && b)
            {
                return 2;
            }
            return 3;
        }

        private readonly IMachine machine;
        private readonly uint[] regs;
        private readonly bool[] pins = new bool[2];
        private uint count;               // kept in the 16-bit range on every edge
        private int idx;

        private const long RegCR1 = 0x00;
        private const long RegSMCR = 0x08;
        private const long RegCCMR1 = 0x18;
        private const long RegCCER = 0x20;
        private const long RegCNT = 0x24;
        private const long RegPSC = 0x28;
        private const long RegARR = 0x2C;
        private const int RegSpace = 0x400;
    }
}
