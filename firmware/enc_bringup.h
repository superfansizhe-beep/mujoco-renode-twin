/* Encoder bring-up harness layout -- twin of imu_bringup.h. Fixed
 * addresses carved by stm32f407.ld so the same words are readable in
 * Renode and, later, through a debugger on the board.
 */
#ifndef ENC_BRINGUP_H
#define ENC_BRINGUP_H

#define ENC_RESULT_BASE 0x2001EE00u   /* 512 B; RAM usable ends here */

#endif /* ENC_BRINGUP_H */
