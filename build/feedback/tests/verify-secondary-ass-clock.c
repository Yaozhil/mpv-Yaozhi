/* Tests the actual production header. Simulation is not an actual screen. */
#include <stdio.h>
#include <math.h>
#include "secondary_ass_clock.h"

static unsigned checks, failures;
static double absval(double x) { return x < 0 ? -x : x; }
static void check(bool pass) { checks++; failures += !pass; }
static int64_t ns(double seconds) { return (int64_t)(seconds * 1e9 + 0.5); }
static int nearest(double x)
{
    int n = (int)x;
    double part = x - n;
    return n + (part > 0.5 || (part == 0.5 && (n & 1)));
}

static unsigned matrix(double hz, double fps, bool jitter)
{
    int divisor = (int)(hz / 120);
    if (divisor * 120 < hz)
        divisor++;
    if (divisor < 1)
        divisor = 1;
    double rate = hz / divisor;
    const int64_t origin = INT64_C(4000000000000000);
    double frame = 1 / fps, interval = 1 / hz;
    double error = 0, last_pts = 0;
    unsigned counter = 0, changes = 0;
    struct secondary_ass_clock clock = {0};
    struct secondary_ass_sampler sampler = {0};
    secondary_ass_clock_set_speed(&clock, 1, origin);
    for (unsigned f = 0; f < fps * 10; f++) {
        double previous = error;
        int repeat = nearest((frame + error) / interval);
        error += frame - repeat * interval;
        for (int i = 0; i < repeat; i++) {
            double media_pts = f * frame - previous + i * interval;
            int64_t wall = origin + ns(counter * interval);
            if (jitter && counter)
                wall += ns(interval * 0.08) * (counter % 2 ? 1 : -1);
            bool reset = secondary_ass_clock_anchor(&clock, media_pts, wall, true);
            if (reset)
                secondary_ass_sampler_reset(&sampler);
            bool changed = secondary_ass_sampler_update(&sampler, &clock, rate,
                                                          wall, ns(interval));
            check(changed == (counter % divisor == 0));
            check(sampler.origin_wall == origin);
            check(sampler.tick == counter / divisor);
            check(sampler.valid && isfinite(sampler.pts));
            if (changed) {
                if (changes) {
                    check(sampler.pts > last_pts);
                    if (!jitter)
                        check(absval(sampler.pts - last_pts - 1 / rate) < 2e-9);
                }
                last_pts = sampler.pts;
                changes++;
            } else {
                check(sampler.pts == last_pts);
            }
            counter++;
        }
    }
    check(changes == (counter + divisor - 1) / divisor);
    return changes;
}

static double ppm(double parts, double fps, double speed)
{
    struct secondary_ass_clock clock = {0};
    const int64_t origin = INT64_C(4000000000000000);
    secondary_ass_clock_set_speed(&clock, speed, origin);
    check(secondary_ass_clock_anchor(&clock, 0, origin, false));
    double drift = parts * 1e-6;
    double final_error = 0;
    for (unsigned f = 1; f <= fps * 600; f++) {
        double time = f / fps;
        int64_t wall = origin + ns(time);
        double projected = secondary_ass_clock_sample(&clock, wall);
        double authority = time * speed * (1 + drift);
        bool reset = secondary_ass_clock_anchor(&clock, authority, wall, false);
        check(!reset);
        // Source authority must change rate without changing position there.
        check(absval(secondary_ass_clock_sample(&clock, wall) - projected) < 1e-12);
        check(absval(clock.phase_rate) <= speed * 0.005 + 1e-15);
        check(clock.speed + clock.phase_rate > 0);
        final_error = absval(authority - secondary_ass_clock_sample(&clock, wall));
    }
    check(final_error <= speed * (absval(drift) * 1.1 + 1e-8));
    return final_error;
}

static void lifecycle(void)
{
    struct secondary_ass_clock clock = {0};
    struct secondary_ass_sampler sampler = {0};
    int64_t origin = INT64_C(4000000000000000);
    secondary_ass_clock_set_speed(&clock, 1, origin);
    check(secondary_ass_clock_anchor(&clock, 10, origin, false));
    check(secondary_ass_sampler_update(&sampler, &clock, 72, origin, ns(1.0 / 144)));
    double before = secondary_ass_clock_sample(&clock, origin + ns(.237));
    secondary_ass_clock_set_speed(&clock, 2, origin + ns(.237));
    check(secondary_ass_clock_sample(&clock, origin + ns(.237)) == before);
    check(absval(secondary_ass_clock_sample(&clock, origin + ns(.238)) - before - .002) < 1e-12);
    int64_t grid = sampler.origin_wall;
    sampler.force = true;
    check(secondary_ass_sampler_update(&sampler, &clock, 72, origin + ns(.238), ns(1.0 / 144)));
    check(sampler.origin_wall == grid && !sampler.force);
    check(!secondary_ass_sampler_update(&sampler, &clock, 72, origin + ns(.238), ns(1.0 / 144)));

    // Slow video does not freeze after the old arbitrary 100ms clamp.
    check(absval(secondary_ass_clock_sample(&clock, origin + ns(2)) - before - (2 - .237) * 2) < 1e-12);

    // Explicit small backward seek, pause and track replacement all invalidate.
    secondary_ass_clock_reset(&clock);
    secondary_ass_sampler_reset(&sampler);
    check(!clock.valid && !sampler.valid);
    check(!secondary_ass_sampler_update(&sampler, &clock, 72, origin + ns(3), ns(1.0 / 144)));
    secondary_ass_clock_set_speed(&clock, 1, origin + ns(3));
    check(secondary_ass_clock_anchor(&clock, 9.990, origin + ns(3), false));
    check(secondary_ass_sampler_update(&sampler, &clock, 72, origin + ns(3), ns(1.0 / 144)));
    check(absval(sampler.pts - 9.990) < 1e-12);
    check(secondary_ass_clock_anchor(&clock, 2, origin + ns(4), false));
    check(absval(secondary_ass_clock_sample(&clock, origin + ns(4)) - 2) < 1e-12);
    check(secondary_ass_clock_anchor(&clock, 2.006, origin + ns(4.006), true));
    check(clock.display_synced);
    // Rate change creates one new sampler origin. Effective-speed correction
    // alone leaves the origin intact and never forces an additional sample.
    check(secondary_ass_sampler_update(&sampler, &clock, 120, origin + ns(4.006), ns(1.0 / 240)));
    grid = sampler.origin_wall;
    secondary_ass_clock_set_speed(&clock, 1.00002, origin + ns(4.007));
    check(!secondary_ass_sampler_update(&sampler, &clock, 120, origin + ns(4.007), ns(1.0 / 240)));
    check(sampler.origin_wall == grid);
    secondary_ass_clock_set_speed(&clock, 0, origin);
    check(!clock.valid);
    check(!secondary_ass_sampler_update(&sampler, &clock, 120, origin, ns(1.0 / 240)));
    check(!sampler.valid);
    secondary_ass_clock_set_speed(&clock, NAN, origin);
    check(!clock.valid);
}

static void gap_and_explicit_rates(void)
{
    const int64_t origin = INT64_C(4000000000000000);
    struct secondary_ass_clock clock = {0};
    struct secondary_ass_sampler sampler = {0};
    secondary_ass_clock_set_speed(&clock, 1, origin);
    // Simulate audio fresh video authority continuing through a quiet/static
    // section. Output gating only suppresses extra draws; it never zeros the
    // enabled clock target or resets the sampler's existing phase.
    for (unsigned frame = 0; frame < 250; frame++) {
        int64_t wall = origin + ns(frame * .04);
        bool reset = secondary_ass_clock_anchor(&clock, frame * .04, wall, false);
        if (reset)
            secondary_ass_sampler_reset(&sampler);
        secondary_ass_sampler_update(&sampler, &clock, 72, wall, ns(1.0 / 144));
        check(clock.valid && sampler.valid);
        check(sampler.origin_wall == origin);
        check(absval(sampler.pts - (sampler.sample_wall - origin) * 1e-9) < 1e-8);
    }
    // Moving output resumes at the next physical refresh, retaining the grid.
    int64_t wall = origin + ns(10);
    check(!secondary_ass_clock_anchor(&clock, 10, wall, false));
    secondary_ass_sampler_update(&sampler, &clock, 72, wall, ns(1.0 / 144));
    check(sampler.origin_wall == origin);
    check(sampler.pts > 9.98 && sampler.pts < 10.02);

    const double rates[] = {24, 60, 72, 82.5, 120, 165, 240, 1000};
    for (unsigned r = 0; r < sizeof(rates) / sizeof(rates[0]); r++) {
        secondary_ass_clock_reset(&clock);
        secondary_ass_sampler_reset(&sampler);
        secondary_ass_clock_set_speed(&clock, 1, origin);
        unsigned changes = 0;
        double last = 0;
        for (unsigned n = 0; n < 720; n++) {
            int64_t now = origin + ns(n / 144.0);
            bool reset = secondary_ass_clock_anchor(&clock, n / 144.0, now, true);
            if (reset)
                secondary_ass_sampler_reset(&sampler);
            bool changed = secondary_ass_sampler_update(&sampler, &clock, rates[r],
                                                         now, ns(1.0 / 144));
            check(sampler.valid && isfinite(sampler.pts));
            check(sampler.origin_wall == origin);
            if (changed) {
                check(!changes || sampler.pts > last);
                last = sampler.pts;
                changes++;
            } else {
                check(sampler.pts == last);
            }
        }
        check(changes <= rates[r] * 5 + 1);
        check(changes <= 720);
    }
}

static void display_feedback_noise(void)
{
    const int64_t origin = INT64_C(4000000000000000);
    struct secondary_ass_clock clock = {0};
    struct secondary_ass_sampler sampler = {0};
    secondary_ass_clock_set_speed(&clock, 1, origin);
    double last = 0;
    for (unsigned n = 0; n < 10000; n++) {
        double noise = n ? ((int)(n % 7) - 3) * 0.001 : 0;
        int64_t wall = origin + ns(n / 144.0 + noise);
        double before = clock.valid ? secondary_ass_clock_sample(&clock, wall) : 0;
        bool reset = secondary_ass_clock_anchor(&clock, n / 144.0, wall, true);
        if (reset)
            secondary_ass_sampler_reset(&sampler);
        else
            check(absval(secondary_ass_clock_sample(&clock, wall) - before) < 1e-12);
        bool changed = secondary_ass_sampler_update(&sampler, &clock, 72, wall, ns(1.0 / 144));
        int64_t expected = sampler.origin_wall + ns((sampler.tick + 1) / 72.0);
        check(absval((double)secondary_ass_sampler_next_wall(&sampler) - expected) < 2);
        if (changed) {
            if (n) {
                check(sampler.pts > last);
                check(absval(sampler.pts - last - 1.0 / 72) < 0.00015);
            }
            last = sampler.pts;
        }
    }
}

int main(void)
{
    const double hz[] = {60, 120, 144, 165, 240, 360};
    const double fps[] = {24000.0 / 1001, 24, 25, 30, 60};
    unsigned cases = 0;
    printf("{\"scope\":\"actual production clock+sampler header, deterministic simulation; not physical screens\",\"matrix\":[");
    for (unsigned h = 0; h < 6; h++) {
        for (unsigned f = 0; f < 5; f++) {
            unsigned stable = matrix(hz[h], fps[f], false);
            unsigned jitter = matrix(hz[h], fps[f], true);
            if (cases++)
                printf(",");
            printf("{\"hz\":%.0f,\"fps\":%.12f,\"stable_changes\":%u,\"jitter_changes\":%u}", hz[h], fps[f], stable, jitter);
        }
    }
    double drift20 = ppm(20, 25, 1);
    double drift2000 = ppm(2000, 25, 1);
    double drift_negative = ppm(-2000, 24, 2);
    double low1 = ppm(20, 1, 1);
    double low6 = ppm(20, 6, 1);
    double low10 = ppm(20, 10, 1);
    lifecycle();
    gap_and_explicit_rates();
    display_feedback_noise();
    printf("],\"ppm_600s_final_error_ms\":{\"20\":%.9f,\"2000\":%.9f,\"negative2000_2x\":%.9f,\"fps1\":%.9f,\"fps6\":%.9f,\"fps10\":%.9f},\"checks\":%u,\"failures\":%u,\"status\":\"%s\"}\n",
           drift20 * 1000, drift2000 * 1000, drift_negative * 1000,
           low1 * 1000, low6 * 1000, low10 * 1000, checks, failures,
           failures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
