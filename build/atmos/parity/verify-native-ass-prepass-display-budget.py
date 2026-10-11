"""Exercise actual fixed-prepass budget coordinates and unchanged deadlines.

CPU-only consumer/helper contract; no Display or GPU acceptance claim.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess

HERE=Path(__file__).resolve().parent
CONFIG=HERE.parents[2]

def sha(raw): return hashlib.sha256(raw).hexdigest()
def git(source,*args):
    return subprocess.check_output(['git','-C',str(source),'-c','core.autocrlf=false',
        '-c','user.name=mpv-Yaozhi','-c','user.email=yaozhi@localhost',*args],timeout=45)

FIXTURE=r'''
#include <stdio.h>
#include <string.h>
#include "video/out/secondary_ass_present_plan.h"
#include "video/out/secondary_ass_flip_budget.h"
static struct secondary_ass_physical state(int hz) {
    int64_t t=INT64_C(1000000000)/hz;
    return (struct secondary_ass_physical){.phase=1000000000,.phase_slot=1,
        .interval=t,.epoch=1,.sync_segment_consistent=true,
        .success_generation=1,.success_contiguous=true,.last_base_slot=99};
}
static int64_t consumer_slot(bool fixed, struct secondary_ass_present_plan plan,
                            struct secondary_ass_physical_point logical) {
    struct { bool secondary_fixed_forecast; } data={fixed}, *in=&data;
    struct secondary_ass_present_plan fixed_prepass_plan=plan;
    struct secondary_ass_physical_point sample=logical;
    (void)in;(void)fixed_prepass_plan;(void)sample;
    return SLOT;
}
static int64_t prepare(struct secondary_ass_physical *p,bool fixed,
    struct secondary_ass_present_plan plan,struct secondary_ass_physical_point logical,
    int64_t now,int64_t F,int64_t duration,int divisor,
    int64_t fresh,int64_t R,int64_t Q) {
    return secondary_ass_physical_cache_sample_prepare(p,now,
        consumer_slot(fixed,plan,logical),divisor,F,duration,divisor*p->interval,
        fresh,R,R+Q,0);
}
static struct secondary_ass_flip_window window(struct secondary_ass_present_plan plan,
    int64_t prepare,int64_t now,int64_t F,int64_t fresh,int64_t R,int64_t Q) {
    return secondary_ass_flip_budget_window(prepare>0&&plan.valid,now,prepare,0,
        plan.submit,plan.deadline,F,R,Q,fresh,1000000);
}
int main(void) {
    int hz[]={60,120,144,165,240,360}, checks=0, recovered=0;
    for(unsigned h=0;h<sizeof(hz)/sizeof(*hz);h++)
    for(int offset=0;offset<=4;offset++) {
        struct secondary_ass_physical p=state(hz[h]), original=p;
        struct secondary_ass_physical_point G=secondary_ass_physical_point_at(&p,101);
        struct secondary_ass_present_plan plan=secondary_ass_present_plan_make_fixed_forecast(&p,G,offset);
        if(!plan.valid||plan.base.slot!=G.slot||plan.target.slot!=G.slot+offset)return 2;
        int div=(hz[h]+119)/120;
        for(int step=-20;step<=50;step++) {
            int64_t now=G.wall+step*p.interval/10;
            int64_t F=G.wall+8*p.interval,duration=10*p.interval;
            int64_t R=400000,Q=300000,fresh=1000000;
            int64_t old=secondary_ass_physical_cache_sample_prepare(&p,now,G.slot,div,F,
                duration,div*p.interval,fresh,R,R+Q,0);
            int64_t got=prepare(&p,true,plan,G,now,F,duration,div,fresh,R,Q);
            int64_t legacy=prepare(&p,false,plan,G,now,F,duration,div,fresh,R,Q);
            if(legacy!=old||(!offset&&got!=old))return 3;
            struct secondary_ass_flip_window w=window(plan,got,now,F,fresh,R,Q);
            if(w.valid) {
                if(w.post_cpu_done>=plan.target.wall||w.reserved_end>=F||
                   plan.base.slot!=G.slot||plan.deadline!=plan.target.wall)return 4;
                if(!old)recovered++;
            }
            if(now>=plan.target.wall&&got)return 5;
            struct secondary_ass_present_plan invalid=plan;invalid.valid=false;
            if(prepare(&p,true,invalid,G,now,F,duration,div,fresh,R,Q))return 6;
            // Existing affordability, duration and real F bounds still veto.
            if(prepare(&p,true,plan,G,now,F,0,div,fresh,R,Q))return 7;
            if(prepare(&p,true,plan,G,now,F,duration,div,duration,R,Q))return 8;
            if(window(plan,got,now,plan.submit+1,fresh,R,Q).valid)return 9;
            if(window(plan,got,now,F,fresh,R,2*p.interval).valid)return 10;
            if(memcmp(&p,&original,sizeof(p)))return 11;
            checks++;
        }
    }
    // Exact queued-prepass counterexample: G expired; original D and F safe.
    struct secondary_ass_physical p=state(165);
    struct secondary_ass_physical_point G=secondary_ass_physical_point_at(&p,101);
    struct secondary_ass_present_plan plan=secondary_ass_present_plan_make_fixed_forecast(&p,G,2);
    int64_t now=G.wall+500000,F=G.wall+25000000;
    int64_t old=secondary_ass_physical_cache_sample_prepare(&p,now,G.slot,2,F,16666666,
        2*p.interval,4000000,400000,700000,0);
    int64_t got=prepare(&p,true,plan,G,now,F,16666666,2,4000000,400000,300000);
    struct secondary_ass_flip_window w=window(plan,got,now,F,4000000,400000,300000);
    if(old||!got||!w.valid||!recovered)return 12;
    for(int offset=-1;offset<=5;offset+=6) {
        struct secondary_ass_present_plan unknown=
            secondary_ass_present_plan_make_fixed_forecast(&p,G,offset);
        if(unknown.valid||prepare(&p,true,unknown,G,now,F,16666666,2,
                                 4000000,400000,300000))return 13;
    }
    struct secondary_ass_physical quarantined=p;quarantined.outlier_pending=true;
    struct secondary_ass_present_plan unknown=
        secondary_ass_present_plan_make_fixed_forecast(&quarantined,G,2);
    if(unknown.valid||prepare(&p,true,unknown,G,now,F,16666666,2,
                             4000000,400000,300000))return 14;
    printf("checks=%d safe_recovered_cases=%d G=%lld D=%lld F=%lld prepare=%lld reserved_end=%lld\n",
        checks,recovered,(long long)G.wall,(long long)plan.target.wall,(long long)F,
        (long long)got,(long long)w.reserved_end);
    return 0;
}
'''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--cc',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply-to-pause',action='store_true',
                    help='Apply the exact locked delta to an already verified pause source')
    a=ap.parse_args();source=a.source.resolve();out=a.output.resolve()
    lock=json.loads((HERE/'source-lock.json').read_bytes())
    fix=lock['native_ass_prepass_fix'];patch=CONFIG/fix['patch']
    assert sha(patch.read_bytes())==fix['patch_sha256']
    assert not git(source,'status','--porcelain').strip()
    if a.apply_to_pause:
        for name,digest in fix['before_source_sha256'].items():
            assert sha((source/name).read_bytes())==digest,name
        git(source,'am','--3way',str(patch))
    assert git(source,'diff','--name-only','HEAD^','HEAD').decode().splitlines()==['video/out/vo.c']
    for name,digest in fix['before_source_sha256'].items():
        assert sha(git(source,'show','HEAD^:'+name))==digest,name
    for name,digest in fix['source_sha256'].items():
        assert sha((source/name).read_bytes())==digest,name
    text=(source/'video/out/vo.c').read_text()
    matches=re.findall(r'int64_t budget_slot = (.*?);',text,re.S);assert len(matches)==1
    slot=matches[0]
    # Check that only the budget receives D: task/sampler identity remains G.
    section=text[text.index('struct secondary_ass_present_plan fixed_prepass_plan ='):]
    section=section[:section.index('secondary_capture_grid_plan(&grid_task);')]
    assert '.point = sample,' in section and 'now, budget_slot, sample_divisor,' in section
    assert '? (in->secondary_fixed_forecast ? fixed_prepass_plan :' in section
    out.parent.mkdir(parents=True,exist_ok=True)
    cases={'candidate':slot,'old_G_coordinate':slot.replace('fixed_prepass_plan.target.slot','sample.slot'),
           'invalid_plan_bypass':slot.replace('fixed_prepass_plan.valid','true')}
    rows=[]
    for name,expr in cases.items():
        for release in (False,True):
            stem=name+('-ndebug' if release else '')
            c=out.parent/(stem+'.c');exe=out.parent/(stem+'.exe')
            c.write_text(FIXTURE.replace('SLOT',expr),encoding='utf-8')
            cmd=[str(a.cc),'-std=c11','-Wall','-Werror','-I'+str(source),'-o',str(exe),str(c)]
            if release:cmd.insert(1,'-DNDEBUG')
            compiled=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
            assert compiled.returncode==0,compiled.stderr
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert (run.returncode==0)==(name=='candidate'),(name,run.returncode,run.stdout)
            rows.append({'case':stem,'returncode':run.returncode,'stdout':run.stdout.strip()})
    report={'status':'CPU_PREPASS_G_D_BUDGET_PASS_NOT_DISPLAY_ACCEPTANCE',
            'source_commit':git(source,'rev-parse','HEAD').decode().strip(),
            'source_tree':git(source,'rev-parse','HEAD^{tree}').decode().strip(),
            'patch_sha256':fix['patch_sha256'],
            'source_sha256':sha((source/'video/out/vo.c').read_bytes()),'cases':rows,
            'runtime_verified':False,'Display_accepted':False,'deployed':False}
    assert not git(source,'status','--porcelain').strip()
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
