// Renode device model: MPU6050 IMU on the I2C bus, counterpart of the
// firmware driver (firmware/mpu6050.c). Register map and reset values
// per InvenSense RM-MPU-6000A; sample data is latched from a scratch
// sysbus region ("imu bench") that the Python harness refreshes every
// coupling period -- the harness plays the ODR pacemaker the physics
// clock plays anyway.
//
// Renode limits, kept visible instead of hidden: a device on this bus
// cannot NACK (the II2CPeripheral contract has no NACK return), so a
// misbehaving DEVICE stays unmodelable; the driver's address-NACK path
// is gated instead through the controller-level AF of i2c_model.cs
// (I2CNackSim), and identity and update liveness fault through this
// bench's fault-injection word. Data-ready is observed by polling INT_STATUS,
// the same register a real board reads even when INT is routed to EXTI.
//
// Loaded at runtime by bot/renode.py -- `include "<this file>"` -- and
// attached by firmware/stm32f407zg.repl as:
//     mpu: I2C.MPU6050Sim @ i2c1 0x68
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.I2C;

namespace Antmicro.Renode.Peripherals.I2C
{
    public class MPU6050Sim : II2CPeripheral
    {
        public MPU6050Sim(IMachine machine, long benchAddress = DefaultBenchAddress)
        {
            this.machine = machine;
            this.benchAddress = benchAddress;
            regs = new byte[NumRegs];
            Reset();
        }

        public void Reset()
        {
            Array.Clear(regs, 0, regs.Length);
            regs[PwrMgmt1] = 0x40;              // SLEEP at power-up, like the real device
            regs[WhoAmI] = DefaultWhoAmI;
            pointer = 0;
            intStatus = 0;
            latchedSeq = 0;
            txCount = 0;
            rxCount = 0;
            stopCount = 0;
            LastWriteHex = "";
        }

        public void Write(byte[] data)
        {
            txCount++;
            LastWriteHex = BitConverter.ToString(data);
            if(data.Length == 0)
            {
                return;
            }
            TryLatch();
            pointer = data[0];
            for(var i = 1; i < data.Length; i++)
            {
                WriteRegister(pointer, data[i]);
                pointer = (byte)((pointer + 1) & PointerWrap);
            }
        }

        public byte[] Read(int count)
        {
            rxCount++;
            var res = new byte[count];
            for(var i = 0; i < count; i++)
            {
                res[i] = ReadRegister(pointer);
                pointer = (byte)((pointer + 1) & PointerWrap);
            }
            return res;
        }

        public void FinishTransmission()
        {
            stopCount++;
        }

        // ---- harness-visible state (asserted from Python via the machine object) ----
        public int TxCount { get { return txCount; } }
        public int RxCount { get { return rxCount; } }
        public int StopCount { get { return stopCount; } }
        public uint LatchedSeq { get { return latchedSeq; } }
        public string LastWriteHex { get; private set; }
        public bool DataReadyBit { get { return (intStatus & 1) != 0; } }
        public byte EffectiveWhoAmI
        {
            get
            {
                var fi = (byte)machine.SystemBus.ReadDoubleWord((ulong)(benchAddress + BenchFi));
                return fi != 0 ? fi : regs[WhoAmI];
            }
        }

        // ---- register map (RM-MPU-6000A) ----
        private const int SmplrtDiv = 0x19;
        private const int Config    = 0x1A;
        private const int GyroConfig = 0x1B;
        private const int AccelConfig = 0x1C;
        private const int IntEnable = 0x38;
        private const int IntStatus = 0x3A;
        private const int AccelXout = 0x3B;     // 14 bytes: accel xyz, temp, gyro xyz
        private const int PwrMgmt1  = 0x6B;     // bit7 DEVICE_RESET, bit6 SLEEP, bits2:0 CLKSEL
        private const int PwrMgmt2  = 0x6C;
        private const int WhoAmI    = 0x75;
        private const byte DefaultWhoAmI = 0x68;
        private const byte PointerWrap = 0x7F;
        private const int NumRegs = 0x80;

        // ---- imu bench layout (shared with the harness; words, little-endian) ----
        public const long DefaultBenchAddress = 0xF0000000;
        private const long BenchMagic = 0x00;
        private const long BenchSeq   = 0x04;
        private const long BenchAccel = 0x08;   // ax ay az gx gy gz temp, int32 raw each (register mapping below)
        private const long BenchFi    = 0x24;   // byte0: whoami override (0 = real), byte1: freeze updates
        private const int BenchMagicValue = 0x494D4231;   // "IMB1"

        private void TryLatch()
        {
            if((int)machine.SystemBus.ReadDoubleWord((ulong)(benchAddress + BenchMagic)) != BenchMagicValue)
            {
                return;
            }
            var fi = machine.SystemBus.ReadDoubleWord((ulong)(benchAddress + BenchFi));
            if((fi & 0x100) != 0)
            {
                return;                         // frozen: samples stop updating
            }
            var seq = machine.SystemBus.ReadDoubleWord((ulong)(benchAddress + BenchSeq));
            if(seq == latchedSeq)
            {
                return;
            }
            if((regs[PwrMgmt1] & 0x40) != 0)
            {
                return;                         // asleep: the device does not sample
            }
            latchedSeq = seq;
            // bench order is the sensor domain (accel xyz, gyro xyz, temp);
            // the register window interleaves temp at 0x41 (RM-MPU-6000A).
            // The bench raw domain is the smallest full-scale (+-2 g /
            // +-250 dps -- bot/sensors.py); the sample carries the
            // full-scale GYRO_CONFIG/ACCEL_CONFIG select at latch time
            // (RM-MPU-6000A 4.1/4.2), so a wider range divides: never
            // saturates. Temp is not scaled; DEVICE_RESET restores the
            // default ranges by clearing the config registers.
            var gyroShift = (regs[GyroConfig] >> 3) & 3;
            var accelShift = (regs[AccelConfig] >> 3) & 3;
            for(var i = 0; i < 7; i++)
            {
                var v = (int)machine.SystemBus.ReadDoubleWord((ulong)(benchAddress + BenchAccel + 4 * i));
                v >>= i < 3 ? accelShift : (i < 6 ? gyroShift : 0);
                var lo = (byte)(v & 0xFF);
                var hi = (byte)((v >> 8) & 0xFF);
                var pair = i < 3 ? i : (i == 6 ? 3 : i + 1);
                regs[AccelXout + 2 * pair] = hi;
                regs[AccelXout + 2 * pair + 1] = lo;
            }
            if((regs[IntEnable] & 1) != 0)
            {
                intStatus |= 1;
            }
        }

        private void WriteRegister(byte addr, byte value)
        {
            if(addr == PwrMgmt1 && (value & 0x80) != 0)
            {
                // DEVICE_RESET: back to power-up defaults immediately
                // (the real device needs ~100 ms; the driver's poll passes)
                var wasAsleep = true;
                Array.Clear(regs, 0, regs.Length);
                regs[PwrMgmt1] = 0x00;          // reset clears SLEEP
                regs[WhoAmI] = DefaultWhoAmI;
                intStatus = 0;
                pointer = 0;
                this.Log(LogLevel.Debug, "DEVICE_RESET (asleep={0})", wasAsleep);
                return;
            }
            switch(addr)
            {
            case SmplrtDiv:
            case Config:
            case GyroConfig:
            case AccelConfig:
            case IntEnable:
            case PwrMgmt1:
            case PwrMgmt2:
                regs[addr] = value;
                break;
            default:
                this.Log(LogLevel.Debug, "write to read-only/register-less 0x{0:X} ignored", addr);
                break;
            }
        }

        private byte ReadRegister(byte addr)
        {
            if(addr == WhoAmI)
            {
                return EffectiveWhoAmI;
            }
            if(addr == IntStatus)
            {
                var v = intStatus;
                intStatus = 0;                  // cleared on read, like the real device
                return (byte)v;
            }
            return regs[addr];
        }

        private readonly IMachine machine;
        private readonly long benchAddress;
        private readonly byte[] regs;
        private byte pointer;
        private byte intStatus;
        private uint latchedSeq;
        private int txCount;
        private int rxCount;
        private int stopCount;
    }
}
