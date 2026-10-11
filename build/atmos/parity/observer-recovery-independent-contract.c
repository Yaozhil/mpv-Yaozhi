#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "secondary_ass_physical.h"
#include "secondary_ass_present_plan.h"

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { \
    fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); exit(4); } } while (0)
static const int64_t origin = INT64_C(1000000000);
static const int64_t qorigin = INT64_C(100000000000);

static struct secondary_ass_physical state(int64_t t)
{
    return (struct secondary_ass_physical){
        .epoch=7, .interval=t, .phase=origin, .phase_slot=100,
        .sync_qpc_ns=qorigin, .sync_slot=100, .sync_count=100,
        .sync_segment_consistent=true, .measure_qpc_ns=qorigin,
        .measure_count=100, .periods={t,t,t,t,t}, .period_count=5,
        .period_next=4, .historical_id=10, .delay=2,
        .delay_samples={1,2,3}, .delay_count=3, .delay_next=1,
        .last_base_slot=101, .last_base=origin+t,
        .submitted={{.id=11,.base=origin+t,.base_slot=101,.target_slot=103}},
        .next=1,
    };
}

static void learner_unchanged(const struct secondary_ass_physical *p,
                              const struct secondary_ass_physical *before)
{
    CHECK(p->delay == before->delay);
    CHECK(p->delay_count == before->delay_count);
    CHECK(p->delay_next == before->delay_next);
    CHECK(!memcmp(p->delay_samples, before->delay_samples, sizeof p->delay_samples));
    CHECK(p->interval == before->interval);
    CHECK(p->period_count == before->period_count);
    CHECK(p->period_next == before->period_next);
    CHECK(!memcmp(p->periods, before->periods, sizeof p->periods));
    CHECK(p->epoch == before->epoch);
    CHECK(p->last_base_slot == before->last_base_slot);
    CHECK(p->last_base == before->last_base);
    CHECK(p->submitted[0].id == before->submitted[0].id);
    CHECK(p->submitted[0].base == before->submitted[0].base);
    CHECK(p->submitted[0].base_slot == before->submitted[0].base_slot);
    CHECK(p->submitted[0].target_slot == before->submitted[0].target_slot);
}

static struct secondary_ass_physical seeded(int64_t t)
{
    struct secondary_ass_physical p = state(t);
    p.outlier_pending=true;
    p.outlier_qpc_ns=qorigin+2*t+2*t/5;
    p.outlier_count=102;
    p.recovery_qpc_ns=p.outlier_qpc_ns;
    p.recovery_count=102;
    p.recovery_slot=102;
    p.sync_segment_consistent=false;
    p.measure_qpc_ns=0;
    p.submitted[0].gap_excluded=true;
    return p;
}

static void single_jitter(int64_t t)
{
    struct secondary_ass_physical p=state(t), before=p;
    int64_t bad=qorigin+2*t+2*t/5;
    CHECK(!secondary_ass_physical_observe(&p,bad,102,t));
    CHECK(p.outlier_pending && p.phase == origin && p.phase_slot == 100);
    CHECK(p.sync_qpc_ns == qorigin && p.sync_count == 100 && p.sync_slot == 100);
    for (unsigned n=0;n<50;n++) {
        CHECK(!secondary_ass_physical_observe(&p,bad,102,t));
        CHECK(p.phase == origin && p.phase_slot == 100);
    }
    CHECK(!secondary_ass_physical_observe(&p,qorigin+3*t,103,t));
    CHECK(!p.outlier_pending && p.phase == origin && p.phase_slot == 100);
    CHECK(p.history_floor_slot == 103 && !p.sync_segment_consistent);
    learner_unchanged(&p,&before);
}

static void duplicate_and_stale_seed(int64_t t)
{
    struct secondary_ass_physical p=seeded(t), before=p;
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns,103));
    CHECK(!memcmp(&p,&before,sizeof p));
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns-1,101));
    CHECK(!memcmp(&p,&before,sizeof p));
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,102));
    CHECK(p.outlier_pending);
    CHECK(p.recovery_count == 102);
    CHECK(p.recovery_qpc_ns == before.recovery_qpc_ns+t);
    CHECK(secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,103));
    CHECK(!p.outlier_pending && p.history_floor_slot == 103);
    learner_unchanged(&p,&before);
}

static void relative_error_gate(int64_t t)
{
    const int64_t residuals[]={t/4,-t/4,t/4+1,-t/4-1};
    for (unsigned n=0;n<4;n++) {
        struct secondary_ass_physical p=seeded(t), before=p;
        bool ok=secondary_ass_physical_recover_displaced(&p,
                p.recovery_qpc_ns+t+residuals[n],103);
        CHECK(ok == (n<2));
        CHECK(p.outlier_pending == (n>=2));
        learner_unchanged(&p,&before);
    }
    struct secondary_ass_physical p=seeded(t);
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,104));
    CHECK(p.outlier_pending); // Time says one period, count says two.
    p=seeded(t);
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+2*t,103));
    CHECK(p.outlier_pending); // Time says two periods, count says one.
    p=seeded(t);
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,
            (uint32_t)(p.recovery_count+UINT32_C(0x80000000))));
    CHECK(p.outlier_pending && p.recovery_qpc_ns == 0);
}

static void slot_floor(int64_t t)
{
    struct secondary_ass_physical p=seeded(t);
    p.last_base_slot=105;
    int64_t bad=p.recovery_qpc_ns;
    for (uint32_t count=103;count<=105;count++) {
        CHECK(!secondary_ass_physical_recover_displaced(&p,
                bad+(count-102)*t,count));
        CHECK(p.outlier_pending && p.sync_slot == 100);
    }
    CHECK(secondary_ass_physical_recover_displaced(&p,bad+4*t,106));
    CHECK(p.sync_slot == 106 && p.history_floor_slot == 106);
    CHECK(p.last_base_slot == 105);
}

static void counter_wrap_and_limits(int64_t t)
{
    struct secondary_ass_physical p=state(t);
    p.sync_count=UINT32_MAX-1;
    int64_t bad=qorigin+2*t+2*t/5;
    CHECK(!secondary_ass_physical_observe(&p,bad,0,t));
    CHECK(p.recovery_slot == 102);
    CHECK(!secondary_ass_physical_observe(&p,bad+t,1,t));
    CHECK(!p.outlier_pending && p.sync_count == 1 && p.sync_slot == 103);
    CHECK(p.phase == 0 && p.phase_slot == 0 && p.epoch == 7);

    p=seeded(t); p.sync_slot=INT64_MAX-1;
    p.recovery_slot=INT64_MAX;
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,103));
    CHECK(p.outlier_pending && p.recovery_qpc_ns == 0);
    p=seeded(t); p.epoch_exhausted=true;
    struct secondary_ass_physical before=p;
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,103));
    CHECK(!memcmp(&p,&before,sizeof p));
    p=seeded(t); p.interval=INT64_MAX;
    before=p;
    CHECK(!secondary_ass_physical_recover_displaced(&p,p.recovery_qpc_ns+t,103));
    CHECK(!memcmp(&p,&before,sizeof p));
    p=seeded(t); p.recovery_qpc_ns=1;
    CHECK(!secondary_ass_physical_recover_displaced(&p,INT64_MAX,103));
    CHECK(p.outlier_pending);
}

static void full_feedback_history_isolation(int64_t t)
{
    struct secondary_ass_physical p=state(t), before=p;
    int64_t bad=qorigin+2*t+2*t/5;
    struct secondary_ass_physical_point none={0};
    secondary_ass_physical_update_observed(&p,false,0,none,
        bad,origin+2*t,102,102,11,t);
    CHECK(p.phase == origin && p.historical_id == 10 && p.outlier_pending);
    secondary_ass_physical_update_observed(&p,false,0,none,
        bad+t,origin+3*t,103,103,11,t);
    CHECK(!p.outlier_pending && p.phase == 0 && p.historical_id == 10);
    CHECK(p.history_floor_slot == 103 && p.submitted[0].gap_excluded);
    learner_unchanged(&p,&before);
    // Offset history from the quarantined submission cannot bootstrap phase.
    secondary_ass_physical_update_observed(&p,false,0,none,
        bad+2*t,origin+4*t,104,103,11,t);
    CHECK(p.phase == 0 && p.historical_id == 10);
    learner_unchanged(&p,&before);
    // Exact Sync/Present is a genuine new wall anchor, not raw QPC copied to ASS.
    secondary_ass_physical_update_observed(&p,false,0,none,
        bad+3*t,origin+5*t,105,105,11,t);
    CHECK(p.phase == origin+5*t && p.phase_slot == 105 && p.historical_id == 11);
    CHECK(p.phase != p.sync_qpc_ns);
    learner_unchanged(&p,&before);
    // Reset cannot reuse the old recovery seed or historical ledger.
    secondary_ass_physical_reset(&p);
    CHECK(p.epoch == 8 && !p.outlier_pending && p.recovery_qpc_ns == 0);
    CHECK(p.history_floor_slot == 0 && p.submitted[0].id == 0);
}

int main(void)
{
    const int rates[]={60,120,144,165,240,360,480};
    for (unsigned n=0;n<sizeof rates/sizeof rates[0];n++) {
        int64_t t=INT64_C(1000000000)/rates[n];
        single_jitter(t);
        duplicate_and_stale_seed(t);
        relative_error_gate(t);
        slot_floor(t);
        full_feedback_history_isolation(t);
        counter_wrap_and_limits(t);
    }
    printf("PASS independent recovery contracts: %u checks, 7 rates, actual helper\n",checks);
    return 0;
}
