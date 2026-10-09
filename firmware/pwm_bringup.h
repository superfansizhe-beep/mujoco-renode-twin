/* PWM bring-up harness layout -- command + results for pwm_bringup.elf.
 * The harness writes signed permille duties into the command block;
 * the firmware applies them every 1 ms tick and echoes what it applied
 * (CCR values + the direction-pin word) back in the results block.
 */
#ifndef PWM_BRINGUP_H
#define PWM_BRINGUP_H

#define PWM_RESULT_BASE 0x2001EC00u   /* 512 B; RAM usable ends here */

#endif /* PWM_BRINGUP_H */
