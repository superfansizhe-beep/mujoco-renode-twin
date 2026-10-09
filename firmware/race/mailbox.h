/* C mirror of race/mailbox.py (RAC2) -- the RAM contract (smart-car race twin).
 *
 * tests/test_race.py pins it down with byte-level cross-checks: every field
 * Python packs must land on the offset declared in this header. Changing the
 * layout = change both sides together + change the magic.
 * Same window as the twin's mailbox.h (top 64B of the F407's real 128K SRAM);
 * the two firmwares each own one Renode machine and never see each other.
 */
#ifndef RACE_MAILBOX_H
#define RACE_MAILBOX_H

#include <stdint.h>

#define RACE_MAILBOX_MAGIC 0x52414332u /* 'RAC2', matches race/mailbox.py MAGIC */
#define RACE_MAILBOX_BASE  0x2001FFC0u /* top-64B window of the F407's real 128K SRAM */

#define RACE_MB16(off)  (*(volatile int16_t  *)(RACE_MAILBOX_BASE + (off)))
#define RACE_MBU16(off) (*(volatile uint16_t *)(RACE_MAILBOX_BASE + (off)))
#define RACE_MB32(off)  (*(volatile uint32_t *)(RACE_MAILBOX_BASE + (off)))
#define RACE_MB32S(off) (*(volatile int32_t  *)(RACE_MAILBOX_BASE + (off)))

/* harness -> firmware (sensor frame, 200 Hz, seq change = data ready) */
#define RACE_MAGIC     RACE_MB32(0x00u)
#define RACE_SEQ       RACE_MB32(0x04u)
#define RACE_ACCEL_X   RACE_MB16(0x08u)  /* MPU6050 raw, +-2g range */
#define RACE_ACCEL_Y   RACE_MB16(0x0Au)
#define RACE_ACCEL_Z   RACE_MB16(0x0Cu)
#define RACE_GYRO_X    RACE_MB16(0x0Eu)  /* +-250dps range */
#define RACE_GYRO_Y    RACE_MB16(0x10u)
#define RACE_GYRO_Z    RACE_MB16(0x12u)
#define RACE_TEMP      RACE_MB16(0x14u)
#define RACE_BATT_MV   RACE_MBU16(0x16u)
#define RACE_ENC_L     RACE_MB32S(0x18u) /* accumulated counts, 1320/rev, + = chassis +Y */
#define RACE_ENC_R     RACE_MB32S(0x1Cu)
#define RACE_LINE_BITS RACE_MBU16(0x20u) /* bit i = bar sensor i on-tape (i grows with x) */
#define RACE_TASK_WORD RACE_MBU16(0x22u) /* byte0 = task 1..4, bit8 = turbo */

/* firmware -> harness (motors + heartbeat + mission-state telemetry) */
#define RACE_DUTY_L    RACE_MB16(0x24u)  /* permille, + = chassis +Y */
#define RACE_DUTY_R    RACE_MB16(0x26u)
#define RACE_BUZZER_MS RACE_MBU16(0x28u) /* remaining beep ms, 0 = silent */
#define RACE_LED       RACE_MBU16(0x2Au) /* bit0 = lit */
#define RACE_FW_SEQ    RACE_MB32(0x2Cu)  /* +1 per control cycle, heartbeat */
#define RACE_STATUS    RACE_MB32(0x30u)  /* byte0 phase(0arm/1run/2brake/
                                          * 3done), byte1 seg_i; bits16-17
                                          * source(0odo/1sensor/2hold), bits18-19
                                          * observation(0lost/1track/2wide/3split),
                                          * bit20 array centered (not heading) */
#define RACE_T_MISSION RACE_MB32(0x34u)  /* mission clock ms (counts up while
                                          * running, frozen at done, 0 pre-start) */
#define RACE_E_LAT_MM  RACE_MB16(0x38u)  /* applied steering error, + tape-left, mm */
#define RACE_V_PLAN    RACE_MBU16(0x3Au) /* planned speed telemetry, mm/s */
#define RACE_ODO_X_CM  RACE_MB16(0x3Cu)  /* odometry telemetry, cm */
#define RACE_ODO_Y_CM  RACE_MB16(0x3Eu)

#endif /* RACE_MAILBOX_H */
