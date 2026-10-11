#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "secondary_ass_physical.h"
#define CHECK(x) do { if (!(x)) {fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 4;} } while (0)

int main(void)
{
    const int hz[] = {60,120,144,165,240,360,480};
    uint64_t checks = 0;
    for (unsigned r = 0; r < sizeof(hz)/sizeof(hz[0]); r++) {
        const int64_t t = 1000000000/hz[r], wall0=1000000000;
        const int64_t qpc0 = 20600000000000LL;
        struct secondary_ass_physical p = {
            .epoch=77,.interval=t,.sync_qpc_ns=qpc0,.sync_count=100,
            .sync_slot=4294967296LL,.phase=wall0,.phase_slot=4294967296LL,
            .historical_id=1,.delay=2,.delay_count=3,.delay_samples={2,2,2},
        };
        int64_t max_lattice_error = 0;
        unsigned quarantine = 0;
        for (int n = 1; n <= hz[r]*300; n++) {
            bool jitter = n % (hz[r]*10) == 1;
            int64_t noise = jitter ? t*2/5 : 0;
            int64_t saved_phase=p.phase,saved_slot=p.phase_slot;
            secondary_ass_physical_update_observed(&p,false,0,
                (struct secondary_ass_physical_point){0},qpc0+n*t+noise,
                wall0+n*t+noise,100+n,100+n,(uint64_t)n+1,t);
            CHECK(p.epoch==77 && !p.epoch_exhausted);
            CHECK(p.interval==t && p.delay==2 && p.delay_count==3 && p.delay_next==0);
            CHECK(p.delay_samples[0]==2 && p.delay_samples[1]==2 && p.delay_samples[2]==2);
            CHECK(p.phase>0 && p.phase_slot>0);
            int64_t err=p.phase-wall0-(p.phase_slot-4294967296LL)*t;
            if (err<0) err=-err;
            if (err>max_lattice_error) max_lattice_error=err;
            CHECK(err==0);
            if (jitter) CHECK(p.phase==saved_phase && p.phase_slot==saved_slot && p.outlier_pending);
            else CHECK(!p.outlier_pending);
            quarantine += p.outlier_pending;
            checks += 10;
        }
        printf("{\"hz\":%d,\"duration_seconds\":300,\"max_phase_lattice_error_ns\":%lld,\"single_jitter_quarantine\":%u,\"resets\":0,\"actual_display_known\":false}\n",hz[r],(long long)max_lattice_error,quarantine);
    }
    printf("{\"CPU_contract_checks\":%llu}\n",(unsigned long long)checks);
    return 0;
}
