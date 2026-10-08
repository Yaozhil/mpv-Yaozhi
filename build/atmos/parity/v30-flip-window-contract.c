#include <limits.h>
#include <stdio.h>
#include <stdint.h>
#include "video/out/secondary_ass_flip_budget.h"

static unsigned checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    fprintf(stderr, "line %d: %s\n", __LINE__, #c); } } while (0)

struct fixture {
    int64_t draw, now, prepare, submit, F, R, Q, C, prior_return, frame_end;
    uint64_t epoch, generation, last_id;
    bool expected_prepass, expected_outer;
};
#include "existing-53-fixtures.h"

static struct secondary_ass_flip_budget observed(void)
{
    struct secondary_ass_flip_budget b = {0};
    CHECK(secondary_ass_flip_budget_observe(&b, true, 31, 3, 71, 1000, 1400, 0));
    CHECK(secondary_ass_flip_budget_observe(&b, true, 31, 3, 72, 2000, 2600, 0));
    CHECK(secondary_ass_flip_budget_observe(&b, true, 31, 3, 73, 3000, 3200, 0));
    CHECK(b.cost == 400 && b.samples.count == 3 && b.last_id == 73);
    return b;
}

static void prefix_tests(void)
{
    struct secondary_ass_flip_budget b = observed();
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 3, 73) == 400);
    CHECK(secondary_ass_flip_budget_cost(&b, 31, 3, 73, 200, 777) == 600);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 30, 3, 73) == 0);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 2, 73) == 0);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 3, 72) == 0);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 0, 3, 73) == 0);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 0, 73) == 0);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 3, 0) == 0);
    CHECK(secondary_ass_flip_budget_post_cpu_cost(NULL, 31, 3, 73) == 0);
    CHECK(secondary_ass_flip_budget_cost(&b, 30, 3, 73, 200, 777) == 777);
    CHECK(!secondary_ass_flip_budget_observe(&b, true, 31, 3, 73, 4000, 4400, 0));
    CHECK(b.cost == 400 && b.last_id == 73);
    b.cost = 0;
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 3, 73) == 0);
    b.cost = -1;
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 3, 73) == 0);
    b.cost = 400; b.samples.count = 0;
    CHECK(secondary_ass_flip_budget_post_cpu_cost(&b, 31, 3, 73) == 0);
}

static void interval_tests(void)
{
    // Frozen draw389: old guard double-charges prepared R; original P fits.
    struct secondary_ass_flip_window w = secondary_ass_flip_budget_window(
        true, 10526205600LL, 10526456853LL, 0, 10528707353LL,
        10534852707LL, 2250500, 373900, 3518300, 1000000);
    CHECK(w.valid && w.prepare == 10526456853LL);
    CHECK(w.cpu_done == 10528707353LL && w.submit == 10528707353LL);
    CHECK(w.post_cpu_done == 10529081253LL && w.reserved_end == 10533599553LL);
    CHECK(!secondary_ass_budget_before_deadline(10528707353LL, 10534852707LL,
                                              3518300, 2624400, 1000000));
    // Frozen draw410 has total F room, but its actual preparation misses S.
    w = secondary_ass_flip_budget_window(true, 10846725800LL, 10845723453LL,
        0, 10848118553LL, 10854860144LL, 2395100, 409400, 3810800, 1000000);
    CHECK(!w.valid && !w.prepare);
    // Preserve strict equality and original baseline; late work cannot borrow S.
    w = secondary_ass_flip_budget_window(true, 10, 20, 25, 30, 50, 5, 5, 10, 4);
    CHECK(w.valid && w.prepare == 25 && w.cpu_done == 30 && w.reserved_end == 49);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 25, 30, 49, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(false, 10, 20, 25, 30, 50, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 26, 20, 25, 30, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 31, 30, 100, 0, 5, 10, 4).valid);
    // R=0: agree with the unchanged budget guard in the non-late original window.
    for (int64_t F = 44; F <= 52; F++) {
        bool old = secondary_ass_budget_before_deadline(30, F, 10, 5, 4);
        w = secondary_ass_flip_budget_window(true, 10, 20, 25, 30, F, 0, 5, 10, 4);
        CHECK(w.valid == old);
    }
    // Unknown Q is never credit. Invalid times/costs and every sum overflow fail.
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 100, 5, 0, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 100, -1, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 100, 5, -1, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 100, 5, 5, -1, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 100, 5, 5, 10, -1).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 0, 20, 0, 30, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 0, 0, 30, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, -1, 30, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 0, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 30, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, INT64_MAX-1, INT64_MAX-1, 0,
                                          INT64_MAX-1, INT64_MAX, 2, 1, 0, 0).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0,
                                          INT64_MAX-2, INT64_MAX, 0, 3, 0, 0).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0,
                                          INT64_MAX-2, INT64_MAX, 0, 1, 2, 0).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0,
                                          INT64_MAX-3, INT64_MAX, 0, 1, 1, 2).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0,
                                          INT64_MAX-3, INT64_MAX, 0, 1, 1, 1).valid);
    CHECK(secondary_ass_flip_budget_window(true, 1, 1, 0,
                                          INT64_MAX-4, INT64_MAX, 0, 1, 1, 1).valid);
}

static void snapshot_tests(unsigned *prepass_pass, unsigned *outer_pass)
{
    for (unsigned i = 0; i < sizeof(fixtures)/sizeof(fixtures[0]); i++) {
        const struct fixture *f = &fixtures[i];
        struct secondary_ass_flip_budget b = {
            .samples = {.count = 3}, .cost = f->Q,
            .epoch = f->epoch, .generation = f->generation, .last_id = f->last_id,
        };
        int64_t Q = secondary_ass_flip_budget_post_cpu_cost(&b, f->epoch,
                                                          f->generation, f->last_id);
        CHECK(Q == f->Q);
        struct secondary_ass_flip_window p = secondary_ass_flip_budget_window(
            true, f->now, f->prepare, 0, f->submit, f->F, f->R, Q, f->C, 1000000);
        CHECK(p.valid == f->expected_prepass);
        *prepass_pass += p.valid;
        struct secondary_ass_flip_window o = secondary_ass_flip_budget_window(
            true, f->prior_return, f->prepare, 0, f->submit, f->frame_end,
            f->R, Q, f->C, 2000000);
        CHECK(o.valid == f->expected_outer);
        *outer_pass += o.valid;
        CHECK(!secondary_ass_flip_budget_window(false, f->now, f->prepare, 0,
                                               f->submit, f->F, f->R, Q, f->C, 1000000).valid);
        CHECK(!secondary_ass_flip_budget_window(true, f->now, f->prepare, 0,
                                               f->submit, f->F, f->R, 0, f->C, 1000000).valid);
    }
    CHECK(*prepass_pass == 4 && *outer_pass == 51);
}

int main(void)
{
    unsigned prepass_pass = 0, outer_pass = 0;
    prefix_tests();
    interval_tests();
    snapshot_tests(&prepass_pass, &outer_pass);
    printf("{\"checks\":%u,\"failures\":%u,\"snapshot_rows\":53,"
           "\"prepass_budget_only_allowed\":%u,\"outer_budget_only_allowed\":%u}\n",
           checks, failures, prepass_pass, outer_pass);
    return failures ? 1 : 0;
}
