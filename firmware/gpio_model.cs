// Renode device model: STM32 GPIO port with AF-input gating for the
// encoder pins (gpioPortC#06/#07 -> TIM3, gpioPortD#12/#13 -> TIM4).
//
// Why: the stock GPIOPort.STM32_GPIOPort forwards externally injected
// pin state to the AF-connected timers unconditionally (probed
// 2026-09-29: MODER=00 and AFRL=AF3 still count quadrature edges,
// output/fidelity/probe2c.log) -- on silicon the timer input only
// exists in MODER=AF with the matching AFRL selection, so a firmware
// with a wrong pin map receives encoder counts in sim that the board
// would never deliver.
//
// What it models: for the pins named by `gatedPins`, OnGPIO reaches
// the port (and so the timer input) only when MODER[pin]=AF(10) and
// AFRL nibble == `gatedAF`. Every other pin passes through the stock
// behavior untouched. IDR on a gated pin outside AF mode stops
// reflecting the injected level -- nobody reads it there (the pins are
// timer inputs only), accepted and documented here.
//
// Loaded at runtime by bot/renode.py (`include "<this file>"`) and
// mapped by firmware/stm32f407zg.repl as:
//     gpioPortC: GPIOPort.GPIOPortAFSim @ sysbus <0x40020800, +0x400>
//         gatedPins: [6, 7]
//         gatedAF: 2
using System;
using System.Collections.Generic;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.GPIOPort;

namespace Antmicro.Renode.Peripherals.GPIOPort
{
    public class GPIOPortAFSim : STM32_GPIOPort, IGPIOReceiver
    {
        public GPIOPortAFSim(IMachine machine,
                             uint modeResetValue = 0,
                             uint outputSpeedResetValue = 0,
                             uint pullUpPullDownResetValue = 0,
                             uint numberOfAFs = 16,
                             List<List<int>> invertedAFPins = null,
                             List<int> gatedPins = null,
                             int gatedAF = -1)
            : base(machine, modeResetValue, outputSpeedResetValue,
                   pullUpPullDownResetValue, numberOfAFs, invertedAFPins)
        {
            this.gatedPins = gatedPins;
            this.gatedAF = gatedAF;
        }

        private readonly List<int> gatedPins;
        private readonly int gatedAF;

        public new void OnGPIO(int number, bool value)
        {
            if(gatedPins != null && gatedPins.Contains(number)
               && !InputAFSelected(number))
            {
                return;      // wrong pin map: the timer input never sees this
            }
            base.OnGPIO(number, value);
        }

        private bool InputAFSelected(int pin)
        {
            var moder = base.ReadDoubleWord(0x00);
            if(((moder >> (2 * pin)) & 0x3) != 0x2)
            {
                return false;
            }
            var afr = base.ReadDoubleWord(pin < 8 ? 0x20 : 0x24);
            return (int)((afr >> (4 * (pin & 0x7))) & 0xF) == gatedAF;
        }
    }
}
