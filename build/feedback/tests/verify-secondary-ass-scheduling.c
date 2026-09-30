#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include "secondary_ass_budget.h"

#define MS(n) ((int64_t)((n) * 1000000.0))

int main(void)
{
    const int64_t tick144 = 1000000000LL / 144;
    const int64_t frame24 = 1000000000LL / 24;
    // The previous per-tick test rejected this affordable 19.2% video cost.
    assert(MS(8) >= tick144 * 0.75);
    assert(secondary_ass_budget_affordable(MS(8), MS(1), frame24, tick144));
    assert(secondary_ass_budget_affordable(MS(24), MS(1), MS(40), tick144));
    // Cached redraw cost and total video+redraw work independently protect VO.
    assert(!secondary_ass_budget_affordable(MS(8), MS(6), frame24, tick144));
    assert(!secondary_ass_budget_affordable(MS(28), MS(1), frame24, tick144));
    assert(!secondary_ass_budget_affordable(MS(33), MS(0), frame24, tick144));
    assert(!secondary_ass_budget_affordable(MS(24), MS(1), MS(33.333), tick144));
    // Unknown cost gets a sample only when the video itself leaves room.
    assert(secondary_ass_budget_affordable(MS(8), 0, frame24, tick144));
    assert(!secondary_ass_budget_affordable(MS(33), 0, frame24, tick144));
    assert(secondary_ass_budget_probe_due(MS(8), frame24, tick144, MS(1000), MS(1000)));
    assert(!secondary_ass_budget_probe_due(MS(8), frame24, tick144, MS(999), MS(1000)));
    assert(!secondary_ass_budget_probe_due(MS(33), frame24, tick144, MS(1000), 0));
    assert(!secondary_ass_budget_probe_due(MS(1), tick144, tick144, MS(1000), 0));
    // Unknown timings and frames at/above the display cadence keep the old guard.
    assert(secondary_ass_budget_affordable(MS(1), 0, -1, tick144));
    assert(!secondary_ass_budget_affordable(MS(8), 0, -1, tick144));
    assert(!secondary_ass_budget_low_fps(2 * tick144, tick144));
    assert(secondary_ass_budget_low_fps(2 * tick144 + 1, tick144));
    assert(!secondary_ass_budget_affordable(MS(8), MS(1), MS(8.333), tick144));
    assert(secondary_ass_budget_affordable(MS(8), MS(1), MS(16.667), MS(16.667)));
    assert(!secondary_ass_budget_affordable(MS(14), MS(1), MS(16.667), MS(16.667)));
    assert(!secondary_ass_budget_affordable(0, 0, frame24, 0));
    assert(!secondary_ass_budget_affordable(-1, 0, frame24, tick144));
    assert(!secondary_ass_budget_affordable(0, -1, frame24, tick144));
    // Reject a tick that would consume the next video's preparation time.
    assert(secondary_ass_budget_before_deadline(MS(20), frame24, MS(8), MS(1), MS(2)));
    assert(!secondary_ass_budget_before_deadline(MS(35), frame24, MS(8), MS(1), MS(2)));
    assert(!secondary_ass_budget_before_deadline(MS(20), MS(31), MS(8), MS(1), MS(2)));
    assert(!secondary_ass_budget_before_deadline(MS(20), MS(20), 0, 0, 0));
    assert(!secondary_ass_budget_before_deadline(MS(20), -1, 0, 0, 0));
    assert(!secondary_ass_budget_before_deadline(0, frame24, -1, 0, 0));
    assert(secondary_ass_budget_before_deadline(INT64_MAX - MS(40), INT64_MAX,
                                               MS(8), MS(1), MS(2)));
    // Simulate twenty seconds of ticker decisions. All allowed ticks preserve
    // preparation headroom; there are substantially more ticks than video frames.
    int ticks = 0, refused = 0;
    for (int n = 0; n < 480; n++) {
        int64_t start = (int64_t)n * frame24;
        int64_t deadline = start + frame24;
        for (int64_t now = start + tick144; now < deadline; now += tick144) {
            if (secondary_ass_budget_before_deadline(now, deadline, MS(8), MS(1), MS(2))) {
                ticks++;
                assert(now + MS(8) + MS(1) + MS(2) < deadline);
            } else {
                refused++;
            }
        }
    }
    assert(ticks >= 480 * 3 && refused >= 480);
    // Alternating file/display formats use the current period immediately.
    const int hz[] = {60, 120, 144, 165, 240};
    const double fps[] = {23.976, 24, 25, 29.97, 30, 50, 59.94, 60, 120, 240};
    for (unsigned h = 0; h < sizeof(hz) / sizeof(hz[0]); h++) {
        int64_t interval = 1000000000LL / hz[h];
        for (unsigned f = 0; f < sizeof(fps) / sizeof(fps[0]); f++) {
            int64_t duration = (int64_t)(1000000000.0 / fps[f]);
            if (secondary_ass_budget_low_fps(duration, interval)) {
                assert(!secondary_ass_budget_affordable((int64_t)(duration * 0.8),
                                                        0, duration, interval));
            } else {
                assert(!secondary_ass_budget_affordable(interval, 0, duration, interval));
            }
        }
    }
    puts("PASS low-fps affordability, total overload, unknown-cost probe, high-fps fallback,");
    puts("     deadline reservation, 20-second cadence and file/display format changes");
    printf("simulated extra ticks=%d refused near deadline=%d\n", ticks, refused);
    return 0;
}
