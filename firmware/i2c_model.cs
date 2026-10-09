// I2C NACK slice: harness-armed acknowledge failure on the I2C1
// controller, for the driver's NACK paths (firmware/stm32f4_i2c.c
// maps SR1.AF -> I2C_ERR_NACK; the IMU bring-up loop reports
// MPU_ERR_I2C and keeps retrying).
//
// Two Renode 1.17 facts force this shape (output/i2c-nack/probe.log):
// the stock STM32F1_I2C sets SR1.AF (0x400) for an address with NO
// registered device (probed 2026-09-29), but Unregister does NOT
// reroute an attached device -- the bus keeps answering -- and SR1
// writes are ignored, so neither detach nor register injection can
// produce the fault. The wrapper therefore ORs AF into SR1 reads while
// armed: every transaction aborts with NACK exactly as an absent
// device would make it, until the harness disarms. The II2CPeripheral
// contract has no NACK return, so a misbehaving DEVICE still cannot be
// modeled -- this is the controller's address-level fault only.
//
// Loaded at runtime by bot/renode.py (`include "<this file>"`) and
// attached by firmware/stm32f407zg.repl as:
//     i2c1: I2C.I2CNackSim @ sysbus 0x40005400
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.I2C;

namespace Antmicro.Renode.Peripherals.I2C
{
    // ReadDoubleWord is only an implicit interface implementation on the
    // stock controller (not C#-virtual), so the subclass re-lists
    // IDoubleWordPeripheral to rebind it; Reset is a true virtual.
    public class I2CNackSim : STM32F1_I2C, IDoubleWordPeripheral
    {
        public I2CNackSim(IMachine machine) : base(machine)
        {
        }

        // arm from the harness: every SR1 read reports acknowledge
        // failure until it is disarmed (machine reset also disarms)
        public bool NackArmed { get; set; }

        public override void Reset()
        {
            base.Reset();
            NackArmed = false;
        }

        public new uint ReadDoubleWord(long offset)
        {
            var v = base.ReadDoubleWord(offset);
            if(NackArmed && offset == RegSR1)
            {
                v |= SR1_AF;
            }
            return v;
        }

        private const long RegSR1 = 0x14;
        private const uint SR1_AF = 1u << 10;
    }
}
