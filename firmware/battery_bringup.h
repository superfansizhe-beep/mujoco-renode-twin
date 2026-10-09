/* Battery bring-up harness layout -- twin of the other bring-up
 * headers. The sample source lives in the Renode bench region
 * (+0x28 battery_mv, +0x2C current_ma -- see adc_model.cs); the
 * results block below is the firmware's report.
 */
#ifndef BATTERY_BRINGUP_H
#define BATTERY_BRINGUP_H

#define BATTERY_RESULT_BASE 0x2001EA00u   /* 512 B; RAM usable ends here */

#endif /* BATTERY_BRINGUP_H */
