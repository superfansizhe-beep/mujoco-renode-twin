// Renode device model: the F4 independent watchdog (0x40003000),
// counterpart of firmware/stm32f4_iwdg.c.
//
// Why a hand model: Renode's Timers.STM32_IndependentWatchdog stores
// the registers but a driven counter NEVER resets the machine (probed
// 2026-09-29: bare KR/PR/RLR drive, 600 ms past the ~300 ms window with
// machine time proven flowing -- zero MachineReset events,
// output/fidelity/probe3.log). The watchdog's whole product is that
// reset; without it a hung loop runs forever in sim while silicon
// would reboot.
//
// What it models (RM0090 ch. 29): the write-only KR state machine
// (0x5555 unlock, 0xCCCC start, 0xAAAA refresh), PR/RLR writable only
// while unlocked, the expiry window (RLR+1) * (4 << PR) LSI cycles,
// and on expiry machine.RequestReset(). Scheduling goes through the
// machine scheduler with a pending-token queue; two Renode 1.17
// runtime-compiler traps probed on the way: a LimitTimer never
// advances in this setup (counter frozen at 1 across 500 ms, enabled
// at construction or later), and a CLOSURE lambda handed to
// ScheduleAction never fires -- only a this-bound method group does
// (output/fidelity/). Reads return 0 (KR write-only, SR's PVU/RVU
// never gate -- PR/RLR apply instantly, no firmware reads SR; CNT is
// not readable on this peripheral, in silicon either).
//
// Loaded at runtime by bot/renode.py (`include "<this file>"`) and
// mapped by firmware/stm32f407zg.repl as:
//     iwdg: Timers.IWDGSim @ sysbus <0x40003000, +0x20>
using System;
using System.Collections.Generic;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Timers
{
    public class IWDGSim : IDoubleWordPeripheral, IKnownSize
    {
        public long Size { get { return 0x400; } }

        public IWDGSim(IMachine machine)
        {
            this.machine = machine;
            Reset();
        }

        public void Reset()
        {
            unlocked = false;
            started = false;
            prescaler = 0;
            reload = 0xFFF;
            pending.Clear();        // stale events must not fire post-reset
            epoch++;
        }

        public uint ReadDoubleWord(long offset)
        {
            return 0;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case 0x00:                      // KR (write-only)
                    if(value == 0x5555)
                    {
                        unlocked = true;
                    }
                    else if(value == 0xAAAA)
                    {
                        if(started)
                        {
                            ScheduleExpiry();   // refresh: restart the window
                        }
                    }
                    else if(value == 0xCCCC)
                    {
                        started = true;
                        unlocked = false;
                        ScheduleExpiry();
                    }
                    else
                    {
                        unlocked = false;       // any other key relocks
                    }
                    break;
                case 0x04:                      // PR
                    if(unlocked)
                    {
                        prescaler = value & 0x7;
                    }
                    break;
                case 0x08:                      // RLR
                    if(unlocked)
                    {
                        reload = value & 0xFFF;
                    }
                    break;
            }
        }

        private void ScheduleExpiry()
        {
            pending.Enqueue(++epoch);
            var ms = (ulong)((reload + 1) * (4L << (int)prescaler) * 1000
                             / (long)LsiHz);
            machine.ScheduleAction(TimeInterval.FromMilliseconds(ms),
                                   HandleWindow, "iwdg-window");
        }

        private void HandleWindow(TimeInterval t)
        {
            if(pending.Count == 0)
            {
                return;             // pre-reset stale event
            }
            var id = pending.Dequeue();
            if(pending.Count > 0 || id != epoch)
            {
                return;             // a newer refresh owns the live window
            }
            this.Log(LogLevel.Error, "IWDG expired -- resetting the machine");
            machine.RequestReset();
        }

        private readonly IMachine machine;
        private readonly Queue<int> pending = new Queue<int>();
        private bool unlocked;
        private bool started;
        private uint prescaler;
        private uint reload;
        private int epoch;

        private const ulong LsiHz = 32000;   // the repl's pinned LSI tree
    }
}
