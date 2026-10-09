// Renode device model: the F4 ADC1 (0x40012000), counterpart of the
// firmware driver (firmware/stm32f4_adc.c). There is no F4 ADC in
// Renode's library (STM32_ADC is the L0/L4 register style), so this
// model implements just the slice the polled one-shot driver uses:
// CR2.SWSTART triggers, SQR3 selects the channel, the conversion
// latches DR with EOC, reading DR clears EOC.
//
// Sample values come from the harness bench region (same one the
// MPU6050 model reads): +0x28 battery_mv for channel 10, +0x2C
// current_ma for channel 11. The board's VBAT divider is part of the
// modeled signal chain (batteryDivider, must equal the firmware's
// VBAT_DIVIDER in stm32f4_adc.h -- the layout test checks it); the
// pin millivolts are quantized to 12 bits against VREF
// (referenceMv, default 3300) and saturate at full scale, like the
// real converter at its rail.
//
// Conversion latency follows the silicon timing (RM0090 rev 22, ch. 13:
// TCONV = sampling + 12 cycles, sampling from SMPR2, ADCCLK = PCLK2 /
// ADCPRE): a repl-attached 16 MHz timer (adcBaud) defers DR+EOC by
// (SMP + 12) x ADCPRE-divider 16 MHz ticks. A SWSTART while a
// conversion is in flight is ignored, and a bus disable (RCC) or
// machine reset drops the in-flight result. Not modeled: watchdog,
// DMA, discontinuous mode, the ADC's power-up delay after ADON.
//
// Loaded at runtime by bot/renode.py -- `include "<this file>"` --
// and attached by firmware/stm32f407zg.repl as:
//     adc1: ADC.ADC1Sim @ sysbus <0x40012000, +0x100>
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Analog
{
    public class ADC1Sim : IDoubleWordPeripheral
    {
        public ADC1Sim(IMachine machine, STM32_Timer convTimer,
                       long benchAddress = DefaultBenchAddress,
                       long referenceMv = DefaultReferenceMv,
                       long batteryDivider = DefaultBatteryDivider)
        {
            this.machine = machine;
            this.convTimer = convTimer;
            this.benchAddress = benchAddress;
            this.referenceMv = referenceMv;
            this.batteryDivider = batteryDivider;
            regs = new uint[RegSpace / 4];
            convTimer.LimitReached += ConversionFire;
            Reset();
        }

        public void Reset()
        {
            Array.Clear(regs, 0, regs.Length);
            conversions = 0;
            LastChannel = 0;
            busy = false;
            generation++;
            convTimer.Enabled = false;
        }

        public uint ReadDoubleWord(long offset)
        {
            var word = Offset(offset);
            if(word == RegDR)
            {
                regs[RegSR] &= ~SR_EOC;     // reading DR clears EOC
                return regs[RegDR];
            }
            return regs[word];
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            var word = Offset(offset);
            if(word == RegCR2)
            {
                regs[RegCR2] = value;
                if((value & CR2_SWSTART) != 0 && (value & CR2_ADON) != 0)
                {
                    StartConversion();
                }
                regs[RegCR2] &= ~CR2_SWSTART;   // self-clears after starting
                return;
            }
            regs[word] = value;
        }

        // ---- harness-visible state ----
        public int Conversions { get { return conversions; } }
        public int LastChannel { get; private set; }
        public uint LastRaw { get { return regs[RegDR]; } }

        // ---- register map (RM0090, ADC1) ----
        private const long RegSR    = 0x00 / 4;
        private const long RegCR1   = 0x04 / 4;
        private const long RegCR2   = 0x08 / 4;
        private const long RegSMPR1 = 0x0C / 4;
        private const long RegSMPR2 = 0x10 / 4;
        private const long RegSQR1  = 0x2C / 4;
        private const long RegSQR3  = 0x34 / 4;
        private const long RegDR    = 0x4C / 4;
        private const long RegSpace = 0x50;
        private const uint SR_EOC      = 1u << 1;
        private const uint CR2_ADON    = 1u << 0;
        private const uint CR2_SWSTART = 1u << 30;

        // ---- bench layout (shared with the harness) ----
        public const long DefaultBenchAddress = 0xF0000000;
        public const long DefaultReferenceMv = 3300;
        public const long DefaultBatteryDivider = 4;   // 30k:10k
        private const long BenchBatteryMv = 0x28;   // channel 10: VBAT sense
        private const long BenchCurrentMa = 0x2C;   // channel 11: current sense
        private const byte ChannelBattery = 10;
        private const byte ChannelCurrent = 11;
        private const int FullScale = 4095;

        private void StartConversion()
        {
            if(busy)
            {
                this.Log(LogLevel.Debug, "SWSTART ignored: conversion in flight");
                return;
            }
            var channel = (byte)(regs[RegSQR3] & 0x1F);
            LastChannel = channel;
            busy = true;
            convGen = generation;
            // TCONV = sampling + 12 cycles (RM0090 ch. 13); channels
            // 10-18 sample from SMPR1 (SMPR2 is channels 0-9 -- the
            // naming is inverted, see the driver's SMPR1_CH), ADCCLK =
            // PCLK2 / ADCPRE (2/4/6/8), and the timer runs at PCLK2, so
            // ticks = cycles x divider. Channels outside SMPR1's window
            // are not wired on this board -- reset sampling time.
            var smp = channel >= 10 && channel <= 18
                ? (int)((regs[RegSMPR1] >> ((channel - 10) * 3)) & 0x7) : 0;
            var cycles = SmpCycles[smp] + 12;
            var divider = AdcpreDivider[(int)((regs[RegCR2] >> 16) & 0x3)];
            convTimer.EventEnabled = true;
            convTimer.Value = 0;
            convTimer.Limit = Math.Max((ulong)(cycles * divider), 1);
            convTimer.Mode = WorkMode.OneShot;
            convTimer.Enabled = true;
        }

        private void ConversionFire()
        {
            if(convGen != generation
               || !machine.SystemBus.IsPeripheralEnabled(this))
            {
                busy = false;      // reset / bus disable dropped the result
                return;
            }
            busy = false;
            var channel = LastChannel;
            long pinMv = 0;
            if(channel == ChannelBattery)
            {
                var batteryMv = (int)machine.SystemBus.ReadDoubleWord(
                    (ulong)(benchAddress + BenchBatteryMv));
                pinMv = batteryMv / batteryDivider;
            }
            else if(channel == ChannelCurrent)
            {
                pinMv = (int)machine.SystemBus.ReadDoubleWord(
                    (ulong)(benchAddress + BenchCurrentMa));
            }
            var raw = pinMv * FullScale / referenceMv;
            if(raw > FullScale)
            {
                raw = FullScale;            // saturate at the rail
            }
            regs[RegDR] = (uint)raw;
            regs[RegSR] |= SR_EOC;
            conversions++;
            this.Log(LogLevel.Debug, "ADC ch{0}: pin {1} mV -> {2}", channel, pinMv, raw);
        }

        private static readonly int[] SmpCycles = { 3, 15, 28, 56, 84, 112, 144, 480 };
        private static readonly int[] AdcpreDivider = { 2, 4, 6, 8 };

        private static long Offset(long byteOffset)
        {
            return byteOffset / 4;
        }

        private readonly IMachine machine;
        private readonly STM32_Timer convTimer;
        private readonly long benchAddress;
        private readonly long referenceMv;
        private readonly long batteryDivider;
        private readonly uint[] regs;
        private int conversions;
        private bool busy;
        private int generation;
        private int convGen;
    }
}
