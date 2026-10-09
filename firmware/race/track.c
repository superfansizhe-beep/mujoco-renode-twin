/* track.c -- the field: projection math over the baked route tables
 * (see track.h). */
#include <math.h>

#include "track.h"

#define TRACK_PI        3.14159265358979f
#define TRACK_TWO_PI_F  6.28318530717959f
#define TRACK_HALF_PI_F 1.57079632679490f

float wrapf(float a)
{
    a = fmodf(a + TRACK_PI, TRACK_TWO_PI_F);
    if (a < 0.0f)
        a += TRACK_TWO_PI_F;
    return a - TRACK_PI;
}

float clampf(float v, float lo, float hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

int clampi(int v, int lo, int hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

void track_project(const race_seg_t *g, float x, float y,
                   float *s, float *lat)
{
    if (!g->is_arc) {
        float dx = x - g->g.s.p0x, dy = y - g->g.s.p0y;
        float t = dx * g->g.s.ux + dy * g->g.s.uy;
        *lat = dx * -g->g.s.uy + dy * g->g.s.ux;
        *s = clampf(t, 0.0f, g->len);
    } else {
        float dx = x - g->g.a.cx, dy = y - g->g.a.cy;
        float r_pt = hypotf(dx, dy);
        float th = atan2f(dy, dx);
        float d = wrapf(th - g->g.a.a0) * g->g.a.dir;
        if (d < 0.0f)
            d += TRACK_TWO_PI_F;
        if (d <= g->g.a.span) {
            *s = g->g.a.r * d;
        } else {
            /* out of sweep: clamp to the nearer end by angular distance
             * (bring-up bug: on a half-circle naive min(d, span) sends
             * points 10 cm before the arc to the far end) */
            *s = (TRACK_TWO_PI_F - d) < (d - g->g.a.span) ? 0.0f : g->len;
        }
        *lat = g->g.a.dir * (g->g.a.r - r_pt);
    }
}

float track_heading(const race_seg_t *g, float s)
{
    if (!g->is_arc)
        return wrapf(g->g.s.psi);
    return wrapf(g->g.a.a0 + g->g.a.dir * (s / g->g.a.r)
                 + g->g.a.dir * TRACK_HALF_PI_F);
}

float track_curvature(const race_seg_t *g, float s)
{
    (void)s;
    return g->is_arc ? g->g.a.dir / g->g.a.r : 0.0f;
}

void track_point(const race_seg_t *g, float s, float *x, float *y)
{
    if (!g->is_arc) {
        *x = g->g.s.p0x + g->g.s.ux * s;
        *y = g->g.s.p0y + g->g.s.uy * s;
    } else {
        float th = g->g.a.a0 + g->g.a.dir * (s / g->g.a.r);
        *x = g->g.a.cx + g->g.a.r * cosf(th);
        *y = g->g.a.cy + g->g.a.r * sinf(th);
    }
}

int track_class(float kappa)
{
    if (fabsf(kappa) < 1e-6f)
        return 0;
    return 1;   /* the field's only taped bends: the two R40 arcs */
}
