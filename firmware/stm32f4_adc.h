/* ADC1 polled one-shot driver -- battery/current sensing.
 *
 * Pin contract (our allocation):
 *   VBAT_SENSE   = PC0 (ADC123_IN10), 30k:10k divider -> VBAT = 4 x pin
 *   CURRENT_SENSE= PC1 (ADC123_IN11), reserved for the current sensor
 * (divider values are board-labeled: measure the real resistors and
 * the VREF rail on arrival, firmware/battery_status.md)
 *
 * The 3S drone battery spans ~9.9 V (empty) to 12.6 V (full); the 4:1
 * divider maps that to 2.48-3.15 V at the pin, inside VREF.
 *
 * ADCPRE stays at its reset /2 (8 MHz ADC clock at the HSI tree) --
 * the common block is not touched and not modeled in Renode.
 */
#ifndef STM32F4_ADC_H
#define STM32F4_ADC_H

#include <stdint.h>

#define ADC_CH_VBAT    10u
#define ADC_CH_CURRENT 11u

#define ADC_VREF_MV    3300u
#define VBAT_DIVIDER   4u

void adc1_init(void);
/* Conversion status is separate from the value: 0 ok, -1 EOC timeout.
 * A raw 0 is a VALID conversion (sense at ground) and must publish --
 * the zero cannot double as the error marker (review 2026-09-29). */
int adc1_read(uint8_t channel, uint16_t *out);       /* raw 0..4095 */
int adc1_read_mv(uint8_t channel, uint32_t *out_mv); /* pin millivolts */
int battery_read_mv(uint32_t *out_mv);               /* divider-high-side mV */

#endif /* STM32F4_ADC_H */
