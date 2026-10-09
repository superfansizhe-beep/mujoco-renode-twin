/* Pure line observation / recovery law; no MMIO or platform dependencies.
 * Eight bits mean BLACK detection, independent of GPIO/LED polarity. */
#ifndef CORE_LINE_H
#define CORE_LINE_H
#include <stdint.h>
#include "../line_config.h"

enum { LINE_LOST, LINE_TRACK, LINE_WIDE, LINE_SPLIT };
enum { LINE_ODOMETRY, LINE_SENSOR, LINE_HOLD };
typedef struct {
    uint8_t bits, count, groups, status, centered;
    float error;
} line_observation_t;
typedef struct {
    float error, last_clean, age;
    uint8_t have_clean, source;
} line_tracker_t;
typedef struct {
    uint32_t white_cycles;
    uint8_t had_clean, candidate;
} line_endpoint_t;

static inline line_observation_t line_observe(uint16_t bits)
{
    line_observation_t o = {0};
    o.bits = (uint8_t)bits;
    float sum = 0.0f;
    for (int i = 0; i < LINE_CFG_COUNT; i++) {
        if (!(o.bits & (1u << i))) continue;
        o.count++;
        if (i == 0 || !(o.bits & (1u << (i - 1)))) o.groups++;
        sum += ((float)i - (LINE_CFG_COUNT - 1) * 0.5f) * LINE_CFG_PITCH;
    }
    o.status = o.count == 0 ? LINE_LOST : o.groups != 1 ? LINE_SPLIT
               : o.count > 4 ? LINE_WIDE : LINE_TRACK;
    if (o.status == LINE_TRACK) {
        o.error = sum / o.count;
        o.centered = o.error > -LINE_CFG_PITCH * 0.25f
                     && o.error < LINE_CFG_PITCH * 0.25f;
    }
    return o;
}

static inline int line_endpoint_update(line_endpoint_t *t, line_observation_t o,
                                      int taped, int late_possible, float dt)
{
    if (!taped || o.status != LINE_LOST) {
        *t = (line_endpoint_t){0};
        t->had_clean = taped && o.status == LINE_TRACK;
        return 0;
    }
    if (t->had_clean) t->candidate = late_possible != 0;
    t->had_clean = 0;
    if (!t->candidate) return 0;
    uint32_t cycles = (uint32_t)(LINE_CFG_END_CONFIRM_S / dt + 0.5f);
    if (cycles == 0) cycles = 1;
    if (t->white_cycles < cycles) t->white_cycles++;
    return t->white_cycles >= cycles;
}

static inline float line_track(line_tracker_t *t, line_observation_t o,
                               float recovery, float dt, int allow_hold)
{
    float target;
    if (o.status == LINE_TRACK) {
        t->last_clean = o.error;
        t->have_clean = 1;
        t->age = 0;
        target = o.error;
        t->source = LINE_SENSOR;
    } else {
        t->age += dt;
        if (allow_hold && t->have_clean && t->age <= LINE_CFG_HOLD_S) {
            target = t->last_clean;
            t->source = LINE_HOLD;
        } else {
            target = recovery;
            t->source = LINE_ODOMETRY;
        }
    }
    if (target > LINE_CFG_ERROR_CAP) target = LINE_CFG_ERROR_CAP;
    if (target < -LINE_CFG_ERROR_CAP) target = -LINE_CFG_ERROR_CAP;
    float delta = (target - t->error) * dt / (LINE_CFG_FILTER_S + dt);
    float bound = LINE_CFG_ERROR_SLEW * dt;
    if (delta > bound) delta = bound;
    if (delta < -bound) delta = -bound;
    t->error += delta;
    return t->error;
}
#endif
