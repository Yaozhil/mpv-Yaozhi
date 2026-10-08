"""Finite V31 actual caller/header CPU checks. No GPU, full ABI or Display claim."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--cc',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
SOURCE=args.source.resolve();CC=args.cc.resolve();OUT=args.output.resolve()
HERE=Path(__file__).resolve().parent
assert not OUT.exists();OUT.mkdir(parents=True)

def sha(data):return hashlib.sha256(data).hexdigest()

PINS={'video/out/vo.c':'4c715652691c8cb2a724594fe3be38a612eb91ace5be8c543e0c2144be43f52e',
      'video/out/secondary_ass_flip_budget.h':'4d8fab468b0c70ed9f85fbbfbe78d5741a3680af9c2dad3d038203755e3e26a9',
      'video/out/secondary_ass_neutral_pose.h':'35141cd6c42907f184fa5f45e4231c0c374ea9e569815a54d040195916c22458',
      'sub/osd.c':'ec81f9cd456171ed0bbe5fc025bf3a4e8a3adf5d92db4ab00c85b78d6c9e63ff',
      'sub/secondary_ass_clock.h':'bf343092600d8793bbab66d04ea83b30c3f793dc11e15fbdf7a08b2b232d70fe',
      'video/out/secondary_ass_physical.h':'d2be57b22c03e0e82e3e0d70c6087b8c07da97a0c4be43eb64c9eee70e9b05db',
      'video/out/secondary_ass_present_plan.h':'3e70702f03bcc899ee21653b82b237b952fdbbd95fb8bc24b5b433d043e2a69d'}
before={p:sha((SOURCE/p).read_bytes()) for p in PINS}
assert before==PINS
vo=(SOURCE/'video/out/vo.c').read_text(encoding='utf-8')

def mask(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m:re.sub(r'[^\n]',' ',m[0]),text,flags=re.S)

def block(text,start):
    masked=mask(text);opening=masked.index('{',start);depth=0
    for i in range(opening,len(text)):
        if masked[i]=='{':depth+=1
        elif masked[i]=='}':
            depth-=1
            if depth==0:return text[start:i+1]
    raise ValueError('Unclosed actual C block')

def function(name):
    matched=re.search(r'(?m)^static (?:void|bool|int64_t) '+name+r'\(',vo)
    assert matched,name
    return block(vo,matched.start())

start=vo.index('            if (in->secondary_fixed_forecast) {',vo.index('static bool render_frame'))
prepass=block(vo,start)
start=vo.index('                if (in->secondary_fixed_forecast) {',vo.index('static MP_THREAD_VOID vo_thread'))
outer=block(vo,start)
assert 'grid_task.plan.deadline' in prepass and 'fixed_cache_plan.deadline' in outer
assert prepass.count('secondary_ass_flip_budget_window(')==outer.count('secondary_ass_flip_budget_window(')==1
snippets={'prepass':prepass,'outer':outer}
for name in ('secondary_cache_post_cpu_cost','secondary_plan_enabled','secondary_trace_flip_window'):
    snippets[name]=function(name)

PREFIX=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include "common/ass_pacing_record.h"
#include "video/out/secondary_ass_flip_budget.h"
#include "video/out/secondary_ass_present_plan.h"
#define MPMAX(a,b) ((a)>(b)?(a):(b))
#define MP_TIME_MS_TO_NS(a) ((int64_t)((a)*1000000))
#define MP_TIME_S_TO_NS(a) ((int64_t)((a)*1000000000))
struct vo_frame { int64_t pts; uint64_t frame_id; };
struct vo_internal {
    bool secondary_split_budget,secondary_fixed_forecast,secondary_present_plan,secondary_present_grid;
    struct secondary_ass_physical secondary_physical;
    struct secondary_ass_flip_budget secondary_flip_budget;
    struct vo_frame *frame_queued,*current_frame;
    int64_t secondary_render_cost,secondary_redraw_cost,flip_queue_offset;
};
struct vo { struct vo_internal *in; struct mpv_global *global; int64_t previous_redraw_time; uint64_t pacing_vo_seq; };
struct secondary_ass_grid_task { struct secondary_ass_present_plan plan; };
static struct mp_ass_pacing_record last_record;
static unsigned logs,checks,failures,model_rates;
static uint64_t model_ticks;
#define CHECK(c) do { checks++; if(!(c)) {failures++;fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c);} } while(0)
bool mp_ass_pacing_enabled(struct mpv_global *g) {(void)g;return true;}
void mp_ass_pacing_record(struct mpv_global *g,uint32_t k,const struct mp_ass_pacing_record *r) {
    (void)g;CHECK(k==MP_ASS_PACING_SPAN);logs++;last_record=*r;
}
'''
WRAPPERS=r'''
static bool actual_prepass(struct vo *vo,struct secondary_ass_present_plan plan,int64_t now,int64_t P) {
    struct vo_internal *in=vo->in;
    struct secondary_ass_grid_task grid_task={plan};
    int64_t prepare=P,sample_divisor=2,prepass_block_cost=100000000;
    @PREPASS@
    return prepare>0;
}
static bool actual_outer(struct vo *vo,struct secondary_ass_present_plan plan,int64_t now,int64_t P,int64_t F,bool baseline) {
    struct vo_internal *in=vo->in;
    int64_t next=P,secondary_deadline=F,secondary_redraw_cost=in->secondary_redraw_cost;
    int64_t secondary_cost=in->secondary_render_cost,cost=100000000,thread_divisor=2,secondary_duration=20000000;
    uint64_t secondary_frame_id=123;
    bool secondary_ds=false,headroom=baseline;
    struct secondary_ass_present_plan fixed_cache_plan=plan;
    @OUTER@
    return headroom;
}
'''.replace('@PREPASS@',prepass).replace('@OUTER@',outer)
TESTS=r'''
struct fixture { struct vo vo;struct vo_internal in;struct vo_frame retained,queued;struct secondary_ass_present_plan plan;int64_t P,F; };
static void init(struct fixture *f) {
    memset(f,0,sizeof *f);logs=0;memset(&last_record,0,sizeof last_record);
    const int64_t T=6944444,phase=1000000000;
    f->vo.in=&f->in;f->vo.pacing_vo_seq=7;
    f->in.secondary_split_budget=f->in.secondary_fixed_forecast=true;
    f->in.secondary_present_grid=f->in.secondary_present_plan=true;
    f->in.secondary_physical=(struct secondary_ass_physical){.phase=phase,.phase_slot=100,.interval=T,
        .epoch=31,.success_generation=3,.success_contiguous=true,.sync_segment_consistent=true};
    f->in.secondary_flip_budget=(struct secondary_ass_flip_budget){.samples={.count=3},.cost=400000,
        .epoch=31,.generation=3,.last_id=73};
    f->in.secondary_physical.success_last_id=73;
    f->in.secondary_redraw_cost=2000000;f->in.secondary_render_cost=3000000;
    f->retained.frame_id=123;f->in.current_frame=&f->retained;
    f->in.frame_queued=&f->queued;f->in.flip_queue_offset=12345;
    f->plan=secondary_ass_present_plan_make_fixed_forecast(&f->in.secondary_physical,
        secondary_ass_physical_point_at(&f->in.secondary_physical,110),0);
    CHECK(f->plan.valid);
    f->P=f->plan.submit-f->in.secondary_redraw_cost;
    f->F=f->plan.deadline+8000000;f->queued.pts=f->F+f->in.flip_queue_offset;
    f->vo.previous_redraw_time=f->P-T-100000;
}
static void actual_callers(void) {
    const int64_t jitter[]={245000,603000};
    for(unsigned mode=0;mode<2;mode++)for(unsigned j=0;j<2;j++) {
        struct fixture f;init(&f);struct secondary_ass_present_plan saved=f.plan;
        int64_t now=f.P+jitter[j];
        bool ok=mode?actual_outer(&f.vo,f.plan,now,f.P,f.F,true):actual_prepass(&f.vo,f.plan,now,f.P);
        CHECK(ok && logs==1 && last_record.v[13]==SECONDARY_ASS_FLIP_WINDOW_ACCEPTED);
        CHECK(last_record.v[0]==350 && last_record.v[1]==(mode?2:1));
        CHECK(last_record.v[2]==now && last_record.v[3]==f.P && last_record.v[4]==2000000);
        CHECK(last_record.v[5]==saved.submit && last_record.v[9]==saved.deadline && last_record.v[8]==f.F);
        CHECK(last_record.v[14]==saved.submit+jitter[j] && last_record.v[15]==saved.submit+jitter[j]+400000);
        CHECK(last_record.v[15]<saved.deadline && last_record.v[15]+3000000+(mode?2000000:1000000)<f.F);
        CHECK(last_record.frame_id==123 && last_record.draw_seq==0 && last_record.epoch==31 && last_record.generation==3);
        CHECK(memcmp(&f.plan,&saved,sizeof saved)==0 && f.queued.pts-f.in.flip_queue_offset==f.F);
    }
    for(unsigned mode=0;mode<2;mode++) {
        struct fixture f;init(&f);
        if(!mode)f.plan.valid=false;
        bool ok=mode?actual_outer(&f.vo,f.plan,f.P,f.P,f.F,false):actual_prepass(&f.vo,f.plan,f.P,f.P);
        CHECK(!ok && logs==1 && last_record.v[13]==SECONDARY_ASS_FLIP_WINDOW_BASELINE_REJECTED);
        init(&f);int64_t now=f.plan.deadline-2000000-400000;
        ok=mode?actual_outer(&f.vo,f.plan,now,f.P,f.F,true):actual_prepass(&f.vo,f.plan,now,f.P);
        CHECK(!ok && last_record.v[13]==SECONDARY_ASS_FLIP_WINDOW_TARGET_MISSED && last_record.v[15]==f.plan.deadline);
        init(&f);f.F=f.plan.submit+400000+3000000+(mode?2000000:1000000);
        f.queued.pts=f.F+f.in.flip_queue_offset;
        ok=mode?actual_outer(&f.vo,f.plan,f.P,f.P,f.F,true):actual_prepass(&f.vo,f.plan,f.P,f.P);
        CHECK(!ok && last_record.v[13]==SECONDARY_ASS_FLIP_WINDOW_VIDEO_RESERVED);
        for(unsigned foreign=0;foreign<5;foreign++) {
            init(&f);
            if(foreign==0)f.in.secondary_flip_budget.cost=0;
            if(foreign==1)f.in.secondary_flip_budget.epoch++;
            if(foreign==2)f.in.secondary_flip_budget.generation++;
            if(foreign==3)f.in.secondary_flip_budget.last_id++;
            if(foreign==4)f.in.secondary_physical.epoch++;
            ok=mode?actual_outer(&f.vo,f.plan,f.P,f.P,f.F,true):actual_prepass(&f.vo,f.plan,f.P,f.P);
            CHECK(!ok && logs==0); // Unknown Q uses untouched conservative fallback; no credit/350 claimed.
        }
    }
    struct secondary_ass_flip_window w=secondary_ass_flip_budget_window(true,INT64_MAX-1,INT64_MAX-1,0,
        INT64_MAX-2,INT64_MAX,INT64_MAX,2,1,0,0);
    CHECK(!w.valid && w.outcome==SECONDARY_ASS_FLIP_WINDOW_OVERFLOW);
    w=secondary_ass_flip_budget_window(true,10,20,0,30,35,100,5,5,10,4);
    CHECK(!w.valid && w.outcome==SECONDARY_ASS_FLIP_WINDOW_TARGET_MISSED && w.post_cpu_done==35);
    w=secondary_ass_flip_budget_window(true,10,20,0,30,36,100,5,5,10,4);
    CHECK(w.valid && w.outcome==SECONDARY_ASS_FLIP_WINDOW_ACCEPTED);
}
static void cadence_models(void) {
    const int rates[]={60,120,144,165,240,360},divisors[]={1,2,2,3,4,6};
    for(unsigned rate=0;rate<6;rate++) {
        int64_t T=1000000000LL/rates[rate],N=divisors[rate],origin=100,phase=1000000000;
        struct secondary_ass_physical p={.phase=phase,.phase_slot=origin,.interval=T,
            .epoch=31,.success_generation=3,.success_contiguous=true,.sync_segment_consistent=true,.delay=0};
        struct secondary_ass_physical saved=p;
        bool all_original=true,all_fit=true,all_held_rejected=true;
        uint64_t count=(uint64_t)(300000000000LL/(N*T));
        for(uint64_t tick=1;tick<=count;tick++) {
            int64_t G=origin+(int64_t)tick*N;
            struct secondary_ass_present_plan plan=secondary_ass_present_plan_make_fixed_forecast(&p,
                secondary_ass_physical_point_at(&p,G),0);
            int64_t R=T/6,Q=T/20,C=T/5,P=plan.submit-R,F=plan.deadline+4000000;
            int64_t jitter=tick%4==0?603000:tick%4==1?245000:tick%4==2?0:-100000;
            struct secondary_ass_flip_window w=secondary_ass_flip_budget_window(plan.valid,P+jitter,P,0,
                plan.submit,plan.deadline,F,R,Q,C,1000000);
            all_original &= plan.base.slot==G && plan.target.slot==G && plan.base.wall==phase+(G-origin)*T;
            all_fit &= w.valid && w.post_cpu_done<plan.deadline && w.reserved_end<F;
            struct secondary_ass_flip_window missed=secondary_ass_flip_budget_window(plan.valid,
                plan.deadline-R-Q,P,0,plan.submit,plan.deadline,F,R,Q,C,1000000);
            all_held_rejected &= !missed.valid && missed.outcome==SECONDARY_ASS_FLIP_WINDOW_TARGET_MISSED;
        }
        CHECK(all_original);CHECK(all_fit);CHECK(all_held_rejected);CHECK(memcmp(&saved,&p,sizeof p)==0);
        model_rates++;model_ticks+=count;
    }
}
int main(void) {
    actual_callers();cadence_models();
    printf("{\"checks\":%u,\"failures\":%u,\"rates\":%u,\"model_seconds_per_rate\":300,\"modeled_ticks\":%llu}\n",
        checks,failures,model_rates,(unsigned long long)model_ticks);
    return failures?1:0;
}
'''
code=PREFIX+'\n'+'\n'.join(snippets[name] for name in ('secondary_cache_post_cpu_cost','secondary_plan_enabled','secondary_trace_flip_window'))+'\n'+WRAPPERS+'\n'+TESTS
actual_path=OUT/'actual-two-callers.c';actual_path.write_text(code,encoding='utf-8',newline='\n')
(OUT/'source-fragments.json').write_text(json.dumps({k:{'sha256':sha(v.encode()),'text':v} for k,v in snippets.items()},indent=2)+'\n',encoding='utf-8')
kind='TCC' if CC.name.lower().startswith('tcc') else 'GCC'
report={'status':'V31_FLIP_WINDOW_CPU_IN_PROGRESS','compiler_kind':kind,'compiler_sha256':sha(CC.read_bytes()),
        'source_sha256':before,'tool_sha256':sha(Path(__file__).read_bytes()),
        'actual_callsite_fragments_sha256':{k:sha(v.encode()) for k,v in snippets.items()},
        'runs':[],'GPU_started':False,'core_compiled':False,'CI_started':False,
        'Display_acceptance':False,'pacing_acceptance':False,'deployment_allowed':False,
        'limits':['Finite complete actual window branches with scalar platform endpoints; not complete VO/Windows ABI.',
                  'Header Q/C are CPU submission estimates, never GPU Ready or Display timestamps.',
                  'Six 300-second physical lattice CPU models are not six physical-monitor long tests.',
                  'Old 53 positive baseline guards are assumed; outer frame-end is approximate and not queued F.',
                  'Original V30 17/15 observable neutral FAILs and complete raw MISS remain unchanged.']}

def execute(path,label,flags):
    if kind=='TCC':
        command=[str(CC),*flags,'-I'+str(SOURCE),'-run',str(path)]
        run=subprocess.run(command,capture_output=True,text=True,timeout=30)
        item={'label':label,'command':command,'compile_and_run':True,'exit_code':run.returncode,
              'stdout':run.stdout,'stderr':run.stderr,'translation_sha256':sha(path.read_bytes())}
    else:
        exe=OUT/(label+'.exe');command=[str(CC),'-std=c11','-O2','-Wall','-Wextra','-Werror',*flags,'-I'+str(SOURCE),str(path),'-lm','-o',str(exe)]
        compiled=subprocess.run(command,capture_output=True,text=True,timeout=30)
        item={'label':label,'compile_command':command,'compile_exit_code':compiled.returncode,
              'compile_stdout':compiled.stdout,'compile_stderr':compiled.stderr,'compiled':compiled.returncode==0,
              'translation_sha256':sha(path.read_bytes())}
        if compiled.returncode==0:
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            item.update({'run_command':[str(exe)],'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr})
        else:item.update({'exit_code':None,'stdout':'','stderr':''})
    report['runs'].append(item)
    try:item['result']=json.loads(item['stdout'])
    except ValueError:item['result']={}
    return item

passed=True
for name,path in (('migrated_320',HERE/'v31-flip-window-contract.c'),('actual_two_callers',actual_path)):
    for flags in ([],['-DNDEBUG']):
        item=execute(path,name+('_NDEBUG' if flags else '_normal'),flags)
        expected=({'checks':320,'failures':0,'snapshot_rows':53,'prepass_budget_only_allowed':41,'outer_budget_only_allowed':52}
                  if name=='migrated_320' else {'checks':105,'failures':0,'rates':6,'model_seconds_per_rate':300,'modeled_ticks':110100})
        item['expected_result']=expected
        passed &= item['exit_code']==0 and item['result']==expected and item['stderr']==''

# Faults change emitted actual caller operands or their original baseline;
# they must compile and then be rejected by the same observable assertions.
mutations=(
    ('prepass_D_replaced_by_F','grid_task.plan.submit, grid_task.plan.deadline,',
     'grid_task.plan.submit, in->frame_queued->pts - in->flip_queue_offset,'),
    ('outer_D_replaced_by_F','fixed_cache_plan.deadline, secondary_deadline,',
     'secondary_deadline, secondary_deadline,'),
    ('prepass_original_F_extended','grid_task.plan.deadline,\n                            in->frame_queued->pts - in->flip_queue_offset,',
     'grid_task.plan.deadline,\n                            in->frame_queued->pts - in->flip_queue_offset + 100000000,'),
    ('outer_original_F_extended','fixed_cache_plan.deadline, secondary_deadline,',
     'fixed_cache_plan.deadline, secondary_deadline + 100000000,'),
    ('prepass_original_baseline_erased','bool baseline = prepare > 0 && grid_task.plan.valid &&\n                        fixed_prepare > 0;',
     'bool baseline = true;'),
    ('outer_original_baseline_erased','bool baseline = headroom && fixed_cache_plan.valid;',
     'bool baseline = true;'),
    ('unknown_Q_given_credit','return secondary_ass_flip_budget_post_cpu_cost(&in->secondary_flip_budget,\n        in->secondary_physical.epoch, in->secondary_physical.success_generation,\n        in->secondary_physical.success_last_id);',
     'return 400000;'),
)
report['source_mutations_rejected']=[]
for name,original,changed in mutations:
    assert code.count(original)==1,(name,code.count(original))
    mutated=code.replace(original,changed,1)
    path=OUT/(name+'.c');path.write_text(mutated,encoding='utf-8',newline='\n')
    item=execute(path,name,[])
    item['negative']=True
    expected_negative={'checks':115 if name=='unknown_Q_given_credit' else 105,
                       'failures':10 if name=='unknown_Q_given_credit' else 1,
                       'rates':6,'model_seconds_per_rate':300,'modeled_ticks':110100}
    item['expected_result']=expected_negative
    rejected=(item['exit_code']==1 and item['result']==expected_negative and bool(item['stderr'])
              and (kind=='TCC' or item.get('compile_exit_code')==0))
    item['compiled_and_runtime_rejected']=rejected
    if rejected:report['source_mutations_rejected'].append(name)
    passed &= rejected
assert {p:sha((SOURCE/p).read_bytes()) for p in PINS}==before
report['status']='V31_FLIP_WINDOW_ACTUAL_CALLERS_CPU_PASS_NOT_DISPLAY' if passed else 'V31_FLIP_WINDOW_CPU_FAIL_RETAINED'
target=OUT/'report.json';target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'report_sha256':sha(target.read_bytes()),'results':[x['result'] for x in report['runs']]}))
raise SystemExit(0 if passed else 1)
