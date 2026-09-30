#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "secondary_ass_budget.h"

#define MS(n) ((int64_t)((n) * 1000000.0))

static int64_t max_ns(int64_t a, int64_t b)
{
    return a > b ? a : b;
}

static int64_t queue_lead(int64_t interval, int64_t fresh)
{
    // vo_is_ready_for_frame submits fresh video before its presentation PTS.
    int64_t lead = max_ns(interval / 2, fresh + MS(2));
    return lead < MS(50) ? lead : MS(50);
}

int main(void)
{
    const int64_t tick144 = 1000000000LL / 144;
    const int64_t frame60 = 1000000000LL / 60;
    const int64_t frame120 = 1000000000LL / 120;
    const int64_t fresh = MS(1);
    const int64_t margin = MS(2);
    const int64_t pts = MS(100);
    const int64_t lead = queue_lead(tick144, fresh);
    int safe60 = 0, refused120 = 0;
    for (int64_t flip_queue = 0; flip_queue <= MS(3); flip_queue += MS(1)) {
        // The tick is anchored to draw submission, not to presentation PTS.
        // Subtract the same flip queue offset as vo_is_ready_for_frame and VO.
        int64_t submit = pts - lead - flip_queue;
        int64_t next = submit + tick144;
        int64_t after_fresh_flip = pts + MS(1);
        int64_t start = max_ns(next, after_fresh_flip);
        int64_t deadline60 = pts + frame60 - flip_queue;
        int64_t deadline120 = pts + frame120 - flip_queue;
        // Unknown redraw cost uses one full display tick conservatively.
        assert(secondary_ass_budget_affordable(fresh, 0, frame60, tick144));
        assert(secondary_ass_budget_headroom(frame60, start, deadline60,
                                             fresh, tick144, margin));
        safe60++;
        // A real sample then drives both utilization and blocking headroom.
        assert(secondary_ass_budget_headroom(frame60, start, deadline60,
                                             fresh, MS(3), margin));
        // 120fps has no safe slot for a full-vsync blocking extra flip.
        // Native video rendering itself still presents ASS on every source frame.
        assert(secondary_ass_budget_affordable(fresh, MS(.25), frame120, tick144));
        assert(!secondary_ass_budget_headroom(frame120, start, deadline120,
                                              fresh, tick144, margin));
        refused120++;
    }
    assert(safe60 == 4 && refused120 == 4);
    // A stalled redraw is optional even when its GPU cost is tiny.
    assert(!secondary_ass_budget_headroom(frame120, pts, pts + frame120,
                                          fresh, MS(7), margin));
    assert(!secondary_ass_budget_headroom(frame60, pts + MS(13), pts + frame60,
                                          fresh, MS(1), margin));
    // A genuinely nonblocking redraw can use a safe high-fps interval.
    assert(secondary_ass_budget_headroom(frame120, pts, pts + frame120,
                                         fresh, MS(.25), margin));
    // Unknown source timing and display-sync callers retain their old fallback.
    assert(secondary_ass_budget_headroom(0, pts, -1, fresh, tick144, margin));
    assert(secondary_ass_budget_headroom(-1, pts, -1, fresh, tick144, margin));
    assert(secondary_ass_budget_affordable(fresh, MS(.25), 0, tick144));
    assert(!secondary_ass_budget_affordable(MS(8), MS(.25), 0, tick144));
    // Twenty seconds at 120fps: every source frame retains the deadline;
    // extra ticker requests that can block one vsync are always refused.
    int refused = 0;
    for (int n = 0; n < 2400; n++) {
        int64_t present = pts + (int64_t)n * frame120;
        int64_t next = present - lead + tick144;
        assert(!secondary_ass_budget_headroom(frame120, next, present + frame120,
                                              fresh, tick144, margin));
        refused++;
    }
    assert(refused == 2400);
    puts("PASS 60fps first redraw sample with real queue lead and flip offsets,");
    puts("     120fps blocking-redraw refusal, safe cheap redraw, unknown/display-sync fallback");
    return 0;
}
