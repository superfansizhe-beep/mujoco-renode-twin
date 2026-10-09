// RCC enable slice for the peripherals used by the production firmware.
// RM0090 rev 22, STM32F405/407 RCC: 7.3.10 AHB1ENR (0x30),
// 7.3.13 APB1ENR (0x40), 7.3.14 APB2ENR (0x44).
// Reference: https://www.st.com/resource/en/reference_manual/dm00031020.pdf
//
// Renode 1.17 probe: SetPeripheralEnabled gates bus accesses, but neither
// clock entries nor externally injected encoder/UART inputs. ClockEntry
// lacks newer Renode's Clocked property; save Enabled and pause entries
// with ExchangeClockEntryWith, preserving CNT and sub-tick residue.
// EncoderCounterSim guards the asynchronous encoder input path; the UART
// asynchronous input gate lives in uart_model.cs (UARTWireSim).
// GPIO AF/output state is retained across clock disable (silicon keeps
// its pin configuration); only its register interface is gated.
//
// Frequencies remain the pinned 16 MHz HSI tree. No PLL/prescaler
// derivation, enable propagation delay, low-power gating or RCC reset-bit
// effects are added. Unused peripherals retain the stock model behavior.
using System;
using System.Collections.Generic;
using System.Linq;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class RCCEnableSim : IDoubleWordPeripheral, IKnownSize
    {
        public RCCEnableSim(IMachine machine, STM32F4_RTC rtcPeripheral,
                            IPeripheral gpioA, IPeripheral gpioB,
                            IPeripheral gpioC, IPeripheral gpioD,
                            IPeripheral gpioE, IPeripheral gpioF,
                            IPeripheral tim1, IPeripheral tim2,
                            IPeripheral tim3, IPeripheral tim4,
                            IPeripheral i2c1, IPeripheral usart2,
                            IPeripheral adc1)
        {
            this.machine = machine;
            stock = new STM32F4_RCC(machine, rtcPeripheral);
            gates = new[] {
                new Gate(0x30, 0, gpioA), new Gate(0x30, 1, gpioB),
                new Gate(0x30, 2, gpioC), new Gate(0x30, 3, gpioD),
                new Gate(0x30, 4, gpioE), new Gate(0x30, 5, gpioF),
                new Gate(0x40, 0, tim2), new Gate(0x40, 1, tim3),
                new Gate(0x40, 2, tim4), new Gate(0x40, 17, usart2),
                new Gate(0x40, 21, i2c1), new Gate(0x44, 0, tim1),
                new Gate(0x44, 8, adc1),
            };
            Reset();
        }

        public long Size { get { return stock.Size; } }
        public GPIO Timer9Reset { get { return stock.Timer9Reset; } }
        public uint ReadDoubleWord(long offset) { return stock.ReadDoubleWord(offset); }

        public void WriteDoubleWord(long offset, uint value)
        {
            stock.WriteDoubleWord(offset, value);
            foreach(var gate in gates.Where(g => g.Offset == offset))
            {
                Apply(gate, (stock.ReadDoubleWord(offset) & (1u << gate.Bit)) != 0);
            }
        }

        public void Reset()
        {
            stock.Reset();
            foreach(var gate in gates)
            {
                // Machine reset also resets the underlying timers. Never
                // restore a pre-reset CEN from a previously suspended clock.
                gate.Suspended.Clear();
                gate.Enabled = false;
                machine.SystemBus.SetPeripheralEnabled(gate.Peripheral, false);
                foreach(var entry in Entries(gate))
                {
                    machine.ClockSource.ExchangeClockEntryWith(entry.Handler,
                        e => e.With(enabled: false));
                }
            }
        }

        private ClockEntry[] Entries(Gate gate)
        {
            return machine.ClockSource.GetAllClockEntries()
                .Where(e => ReferenceEquals(e.Owner, gate.Peripheral)).ToArray();
        }

        private void Apply(Gate gate, bool enabled)
        {
            if(gate.Enabled == enabled)
            {
                return;
            }
            machine.SystemBus.SetPeripheralEnabled(gate.Peripheral, enabled);
            if(enabled)
            {
                foreach(var saved in gate.Suspended)
                {
                    machine.ClockSource.ExchangeClockEntryWith(saved.Key,
                        e => e.With(enabled: saved.Value));
                }
                gate.Suspended.Clear();
            }
            else
            {
                foreach(var entry in Entries(gate))
                {
                    gate.Suspended[entry.Handler] = entry.Enabled;
                    machine.ClockSource.ExchangeClockEntryWith(entry.Handler,
                        e => e.With(enabled: false));
                }
            }
            gate.Enabled = enabled;
        }

        private class Gate
        {
            public Gate(long offset, int bit, IPeripheral peripheral)
            {
                Offset = offset;
                Bit = bit;
                Peripheral = peripheral;
            }
            public readonly long Offset;
            public readonly int Bit;
            public readonly IPeripheral Peripheral;
            public bool Enabled;
            public readonly Dictionary<Action, bool> Suspended = new Dictionary<Action, bool>();
        }

        private readonly IMachine machine;
        private readonly STM32F4_RCC stock;
        private readonly Gate[] gates;
    }
}
