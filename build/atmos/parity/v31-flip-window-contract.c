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
#include "frozen-v30-existing-53-fixtures.h"
static const int64_t original_D[53] = {10534650904LL,10631859204LL,10854062104LL,11034600504LL,11131811904LL,11173443055LL,11534519004LL,11673399604LL,11853935080LL,12034485580LL,12173339280LL,12534458680LL,13034360764LL,13353788664LL,13534314064LL,13631536964LL,13673214264LL,13714851855LL,13853721964LL,13950940740LL,13992617240LL,14034252225LL,14131471140LL,14173156840LL,14214796425LL,14353654040LL,14534186740LL,14714740140LL,15034150540LL,15214673340LL,15714634996LL,16034067040LL,16214577940LL,16714513612LL,17033918312LL,17214459212LL,17533872488LL,17672756888LL,17714401135LL,17853304988LL,18033809380LL,18214367180LL,18714282188LL,18894833788LL,19214229888LL,19353121388LL,19394776535LL,19714186752LL,19853076752LL,19894727865LL,20033604624LL,20214131424LL,20394664624LL};
static const bool expected_prepass_D[53] = {true,false,true,true,false,true,true,false,true,true,true,true,true,false,true,false,true,true,true,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,false,true,true,true,true,true,true,true,true,true,true,true,false,true,true,true};
static const bool expected_outer_D[53] = {true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true};

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
    struct secondary_ass_flip_window w = secondary_ass_flip_budget_window(true, 10526205600LL, 10526456853LL, 0, 10528707353LL, 10534650904LL, 10534852707LL, 2250500, 373900, 3518300, 1000000);
    CHECK(w.valid && w.prepare == 10526456853LL);
    CHECK(w.cpu_done == 10528707353LL && w.submit == 10528707353LL);
    CHECK(w.post_cpu_done == 10529081253LL && w.reserved_end == 10533599553LL);
    CHECK(!secondary_ass_budget_before_deadline(10528707353LL, 10534852707LL,
                                              3518300, 2624400, 1000000));
    // Frozen draw410 is late for preferred S; it still fits original D and F.
    w = secondary_ass_flip_budget_window(true, 10846725800LL, 10845723453LL, 0, 10848118553LL, 10854062104LL, 10854860144LL, 2395100, 409400, 3810800, 1000000);
    CHECK(w.valid && w.prepare==10846725800LL && w.submit==10849120900LL && w.post_cpu_done<10854062104LL);
    // Preserve strict original D/F equality and baseline; late S may still fit original D.
    w = secondary_ass_flip_budget_window(true, 10, 20, 25, 30, 40, 50, 5, 5, 10, 4);
    CHECK(w.valid && w.prepare == 25 && w.cpu_done == 30 && w.reserved_end == 49);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 25, 30, 40, 49, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(false, 10, 20, 25, 30, 40, 50, 5, 5, 10, 4).valid);
    CHECK(secondary_ass_flip_budget_window(true, 26, 20, 25, 30, 40, 100, 5, 5, 10, 4).valid);
    CHECK(secondary_ass_flip_budget_window(true, 10, 20, 31, 30, 40, 100, 0, 5, 10, 4).valid);
    // R=0: agree with the unchanged budget guard in the non-late original window.
    for (int64_t F = 44; F <= 52; F++) {
        bool old = secondary_ass_budget_before_deadline(30, F, 10, 5, 4);
        w = secondary_ass_flip_budget_window(true, 10, 20, 25, 30, 40, F, 0, 5, 10, 4);
        CHECK(w.valid == old);
    }
    // Unknown Q is never credit. Invalid times/costs and every sum overflow fail.
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 40, 100, 5, 0, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 40, 100, -1, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 40, 100, 5, -1, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 40, 100, 5, 5, -1, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 40, 100, 5, 5, 10, -1).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 0, 20, 0, 30, 40, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 0, 0, 30, 40, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, -1, 30, 40, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 0, 40, 100, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 10, 20, 0, 30, 40, 30, 5, 5, 10, 4).valid);
    CHECK(!secondary_ass_flip_budget_window(true, INT64_MAX-1, INT64_MAX-1, 0, INT64_MAX-1, INT64_MAX, INT64_MAX, 2, 1, 0, 0).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0, INT64_MAX-2, INT64_MAX, INT64_MAX, 0, 3, 0, 0).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0, INT64_MAX-2, INT64_MAX, INT64_MAX, 0, 1, 2, 0).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0, INT64_MAX-3, INT64_MAX, INT64_MAX, 0, 1, 1, 2).valid);
    CHECK(!secondary_ass_flip_budget_window(true, 1, 1, 0, INT64_MAX-3, INT64_MAX, INT64_MAX, 0, 1, 1, 1).valid);
    CHECK(secondary_ass_flip_budget_window(true, 1, 1, 0, INT64_MAX-4, INT64_MAX, INT64_MAX, 0, 1, 1, 1).valid);
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
        struct secondary_ass_flip_window p = secondary_ass_flip_budget_window(true, f->now, f->prepare, 0, f->submit, original_D[i], f->F, f->R, Q, f->C, 1000000);
        CHECK(p.valid == expected_prepass_D[i]);
        *prepass_pass += p.valid;
        struct secondary_ass_flip_window o = secondary_ass_flip_budget_window(true, f->prior_return, f->prepare, 0, f->submit, original_D[i], f->frame_end, f->R, Q, f->C, 2000000);
        CHECK(o.valid == expected_outer_D[i]);
        *outer_pass += o.valid;
        CHECK(!secondary_ass_flip_budget_window(false, f->now, f->prepare, 0, f->submit, original_D[i], f->F, f->R, Q, f->C, 1000000).valid);
        CHECK(!secondary_ass_flip_budget_window(true, f->now, f->prepare, 0, f->submit, original_D[i], f->F, f->R, 0, f->C, 1000000).valid);
    }
    CHECK(*prepass_pass == 41 && *outer_pass == 52);
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
