/* C mirror of twin/mailbox.py v2 — RAM contract (balance-bot twin).
 *
 * tests/test_twin.py pins it with byte-level cross-checks: every field
 * packed by Python must land at the offset declared in this header. A
 * layout change = change both sides together + bump the magic.
 */
#ifndef TWIN_MAILBOX_H
#define TWIN_MAILBOX_H

#include <stdint.h>

#define TWIN_MAILBOX_MAGIC 0x54574E32u /* 'TWN2', matches twin/mailbox.py MAGIC */
#define TWIN_MAILBOX_BASE  0x2001FFC0u /* top 64B window of the F407's real 128K SRAM */

#define TWIN_MB16(off)  (*(volatile int16_t  *)(TWIN_MAILBOX_BASE + (off)))
#define TWIN_MBU16(off) (*(volatile uint16_t *)(TWIN_MAILBOX_BASE + (off)))
#define TWIN_MB32(off)  (*(volatile uint32_t *)(TWIN_MAILBOX_BASE + (off)))
#define TWIN_MB32S(off) (*(volatile int32_t  *)(TWIN_MAILBOX_BASE + (off)))

/* harness -> firmware (sensor frame, 200 Hz, seq change = data ready) */
#define TWIN_MAGIC    TWIN_MB32(0x00u)
#define TWIN_SEQ      TWIN_MB32(0x04u)
#define TWIN_ACCEL_X  TWIN_MB16(0x08u)  /* MPU6050 raw, +-2g range */
#define TWIN_ACCEL_Y  TWIN_MB16(0x0Au)
#define TWIN_ACCEL_Z  TWIN_MB16(0x0Cu)
#define TWIN_GYRO_X   TWIN_MB16(0x0Eu)  /* +-250dps range */
#define TWIN_GYRO_Y   TWIN_MB16(0x10u)
#define TWIN_GYRO_Z   TWIN_MB16(0x12u)
#define TWIN_TEMP     TWIN_MB16(0x14u)
#define TWIN_BATT_MV  TWIN_MBU16(0x16u)
#define TWIN_ENC_L    TWIN_MB32S(0x18u) /* cumulative counts, 1320/rev, + = forward */
#define TWIN_ENC_R    TWIN_MB32S(0x1Cu)

/* firmware -> harness (motors + heartbeat) */
#define TWIN_DUTY_L   TWIN_MB16(0x20u)  /* permille, + = forward */
#define TWIN_DUTY_R   TWIN_MB16(0x22u)
#define TWIN_FW_SEQ   TWIN_MB32(0x24u)  /* +1 per control cycle, heartbeat */

#endif /* TWIN_MAILBOX_H */
