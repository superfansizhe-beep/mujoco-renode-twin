/* IMU bring-up harness layout -- the firmware-visible side of
 * imu_bringup.elf's reporting, shared by the C app and the Python
 * tests. Fixed addresses carved out of SRAM by stm32f407.ld so the
 * same words are readable in Renode (sysbus) and, later, on the board
 * through a debugger at identical addresses.
 *
 * Two directions, one block each:
 *   0xF0000000  imu bench (SIMULATION ONLY): the Renode MPU6050 model
 *               latches samples + fault injection from here; the
 *               firmware never touches this region
 *   0x2001F000  results + init trace: the firmware writes, the harness
 *               reads
 */
#ifndef IMU_BRINGUP_H
#define IMU_BRINGUP_H

#define IMU_BENCH_BASE 0xF0000000u   /* words: magic seq ax ay az gx gy gz temp fi */
#define IMU_BENCH_MAGIC 0x494D4231u  /* "IMB1" */
#define IMU_BENCH_FI    0x24u        /* byte0 whoami override (0=real), byte1 freeze */

#define IMU_RESULT_BASE 0x2001F000u
#define IMU_TRACE_BASE  0x2001F080u   /* results block owns 0x80 bytes */
#define IMU_TRACE_CAP   512u         /* u32 entries after the 2-word header */

#endif /* IMU_BRINGUP_H */
