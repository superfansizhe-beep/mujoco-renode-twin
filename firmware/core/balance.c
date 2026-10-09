/* balance.c -- the balance control law, one source for both firmware
 * shells. Constants come from twin_fwconfig.h (generated): the same
 * single source the race header includes and the LQR gains were
 * derived into. */
#include <math.h>

#include "balance.h"
#include "twin_fwconfig.h"

#define BALANCE_PI        3.14159265358979f
#define BALANCE_TWO_PI_F  6.28318530717959f

float balance_tilt_raw(int16_t ay, int16_t az)
{
    return atan2f((float)ay, (float)az);
}

float balance_gyro_rad(int16_t gx)
{
    return (float)gx / TWIN_GYRO_LSB_PER_DPS * (BALANCE_PI / 180.0f);
}

float balance_filter_step(balance_tilt_t *f, float tilt, float gyro_rad)
{
    if (!f->have) {
        f->theta = tilt;
        f->have = 1;
    }
    f->theta = TWIN_ALPHA_F * (f->theta + gyro_rad * TWIN_DT_S)
             + (1.0f - TWIN_ALPHA_F) * tilt;
    return f->theta;
}

float balance_tau(float y, float ydot, float th_err, float thdot)
{
    return -(TWIN_K_LQR_0 * y + TWIN_K_LQR_1 * ydot
             + TWIN_K_LQR_2 * th_err + TWIN_K_LQR_3 * thdot);
}

int balance_duty(float tau, uint16_t batt_mv)
{
    if (batt_mv < 1000u)
        return 0;
    float v_batt = (float)batt_mv / 1000.0f;
    float max_tau = TWIN_STALL_NM * v_batt / TWIN_V_NOM;
    int duty = (int)lroundf(1000.0f * tau / max_tau);
    if (duty >  TWIN_DUTY_CAP_PM) duty =  TWIN_DUTY_CAP_PM;
    if (duty < -TWIN_DUTY_CAP_PM) duty = -TWIN_DUTY_CAP_PM;
    return duty;
}

void balance_hold_init(balance_hold_t *h)
{
    h->tilt.have = 0;
    h->have_enc = 0;
    h->last_enc_mean = 0.0f;
    h->pos_m = 0.0f;
}

int balance_hold_step(balance_hold_t *h, const balance_sample_t *s)
{
    float gyro_x = balance_gyro_rad(s->gx);
    float theta = balance_filter_step(&h->tilt,
                                      balance_tilt_raw(s->ay, s->az),
                                      gyro_x);

    /* encoder differencing -> wheel speed/position (first sample only
     * builds the baseline) */
    float enc_mean = ((float)s->enc_l + (float)s->enc_r) * 0.5f;
    float wheel_rate = 0.0f;
    if (h->have_enc) {
        float d = enc_mean - h->last_enc_mean;
        wheel_rate = d / TWIN_COUNTS_PER_REV * BALANCE_TWO_PI_F / TWIN_DT_S;
        h->pos_m += d / TWIN_COUNTS_PER_M;
    }
    h->last_enc_mean = enc_mean;
    h->have_enc = 1;
    float speed_mps = wheel_rate * TWIN_WHEEL_R_M;

    float tau = balance_tau(h->pos_m, speed_mps,
                            theta - TWIN_THETA_REF_RAD, gyro_x);
    return balance_duty(tau, s->batt_mv);
}
