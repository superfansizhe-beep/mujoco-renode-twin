// Renode device model: TIM1 (0x40010000), the motor PWM timer.
//
// The stock Timers.STM32_Timer carries the whole PWM behavior this
// repo's gates measure (channel duty on the AF-connected pins) but does
// NOT store BDTR: a write of MOE reads back 0 (probed 2026-09-29,
// output/pwm-milestone/pwmprobe.log). Silicon gates the channel outputs
// on BDTR.MOE (RM0090 26.3.5) -- without a readback, the drive-chain
// decode cannot see the main output enable, and a firmware that forgets
// MOE drives motors in sim that would stay dead on the board.
//
// STM32_Timer's accessors are interface-final (not C#-virtual), so this
// subclass re-declares the interfaces to re-map the register access to
// itself and only adds BDTR storage (0x44); everything else is the
// stock model. The plant decode (twin/renode_backend.decode_duty_pair)
// reads MOE from here. The waveform layer (pin duty in the pwm bring-up
// suite) still ignores MOE -- that layer stays the board label.
//
// Loaded at runtime by bot/renode.py (`include "<this file>"`) and
// mapped by firmware/stm32f407zg.repl as:
//     timer1: Timers.TIM1Sim @ sysbus 0x40010000
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.Timers
{
    public class TIM1Sim : STM32_Timer, IDoubleWordPeripheral, IPeripheral
    {
        public TIM1Sim(IMachine machine, ulong frequency, uint initialLimit)
            : base(machine, frequency, initialLimit)
        {
        }

        public uint ReadDoubleWord(long offset)
        {
            return offset == RegBDTR ? bdtr : base.ReadDoubleWord(offset);
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset == RegBDTR)
            {
                bdtr = value;
                return;
            }
            base.WriteDoubleWord(offset, value);
        }

        public void Reset()
        {
            base.Reset();
            bdtr = 0;
        }

        private uint bdtr;
        private const long RegBDTR = 0x44;
    }
}
