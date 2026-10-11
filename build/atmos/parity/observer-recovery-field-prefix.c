// Three clock/count observations reproduce the verified recovery failure.
// No user path, title, raw recording or actual Display acceptance is included.
#include <stdio.h>
#include <string.h>
#include "secondary_ass_physical.h"
#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 4; } } while (0)

int main(void)
{
    struct observation {
        int64_t qpc, wall;
        uint32_t sync, present;
        uint64_t id;
    };
    static const struct observation observations[] = {
        {20666404894700LL,37330061700LL,4930619,4930619,1269},
        {20666409045900LL,37334212900LL,4930620,4930620,1270},
        {20666438238500LL,37363405500LL,4930627,4930627,1271},
    };
    const int64_t t=4166585;
    struct secondary_ass_physical p={
        .epoch=614,.interval=t,.sync_qpc_ns=20666362108100LL,
        .sync_count=4930610,.sync_slot=4294968928LL,
        .phase=37287275100LL,.phase_slot=4294968928LL,
        .delay=2,.delay_count=3,.delay_samples={2,2,2},
        .historical_id=1267,.last_base_slot=4294968937LL,.next=1,
        .submitted={{.id=1268,.base=37325628890LL,
            .base_slot=4294968937LL,.target_slot=4294968937LL}},
    }, before=p;
    bool recovery_call_observation=false;
    for (unsigned n=0;n<3;n++) {
        const struct observation *o=&observations[n];
        if (n==1) {
            struct secondary_ass_physical probe=p;
            // A successful recovery must still quarantine this observation.
            recovery_call_observation=secondary_ass_physical_observe(&probe,o->qpc,o->sync,t);
            CHECK(!recovery_call_observation && !probe.outlier_pending);
            CHECK(probe.phase==0 && probe.phase_slot==0);
        }
        secondary_ass_physical_update_observed(&p,false,0,
            (struct secondary_ass_physical_point){0},o->qpc,o->wall,
            o->sync,o->present,o->id,t);
        CHECK(p.epoch==614 && !p.epoch_exhausted && p.interval==t);
        CHECK(p.delay==2 && p.delay_count==3 && p.delay_next==0);
        CHECK(!memcmp(p.delay_samples,before.delay_samples,sizeof p.delay_samples));
        CHECK(p.last_base_slot==before.last_base_slot && p.last_base==before.last_base);
        CHECK(p.submitted[0].id==before.submitted[0].id);
        CHECK(p.submitted[0].base==before.submitted[0].base);
        CHECK(p.submitted[0].base_slot==before.submitted[0].base_slot);
        CHECK(p.submitted[0].target_slot==before.submitted[0].target_slot);
        CHECK(p.submitted[0].gap_excluded);
        if (n==0) CHECK(p.outlier_pending && p.phase==before.phase);
        if (n==1) CHECK(!p.outlier_pending && p.phase==0 && p.historical_id==1267);
        if (n==2) CHECK(!p.outlier_pending && p.phase==o->wall &&
            p.phase_slot==4294968945LL && p.historical_id==1271 &&
            p.phase!=p.sync_qpc_ns);
    }
    printf("{\"observations\":3,\"recovery_call_observation\":false,"
           "\"H_and_gap_coordinates_unchanged\":true,\"epoch_unchanged\":true,"
           "\"final_phase_ns\":%lld,\"final_phase_slot\":%lld,\"actual_display_known\":false}\n",
           (long long)p.phase,(long long)p.phase_slot);
    return 0;
}
