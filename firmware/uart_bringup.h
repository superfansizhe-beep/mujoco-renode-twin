#ifndef UART_BRINGUP_H
#define UART_BRINGUP_H

/* results block in the ld SRAM carve (see stm32f407.ld): after the
 * imu trace end (0x2001F080 + 0x808), clear of the fault words */
#define UART_RESULT_BASE 0x2001FA00u

#endif /* UART_BRINGUP_H */
