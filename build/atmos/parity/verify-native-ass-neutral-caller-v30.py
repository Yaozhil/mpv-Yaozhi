"""Execute exact V30 caller fragments with explicit CPU/platform endpoints."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--cc', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
CORE = args.source.resolve()
CC = args.cc.resolve()
HERE = args.output.resolve()
assert not HERE.exists()
HERE.mkdir(parents=True)
REPORT = HERE/'actual-neutral-caller.json'
compiler_kind = 'TCC' if CC.name.lower().startswith('tcc') else 'GCC'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

paths = [CORE/'video/out/vo.c', CORE/'video/out/secondary_ass_flip_budget.h',
         CORE/'video/out/secondary_ass_neutral_pose.h', CORE/'sub/osd.c',
         CORE/'sub/secondary_ass_clock.h', CORE/'video/out/secondary_ass_physical.h',
         CORE/'video/out/secondary_ass_present_plan.h']
inputs = {str(p): sha(p) for p in paths}
vo = paths[0].read_text()
osd = (CORE/'sub/osd.c').read_text()

def braced(text, start):
    brace = text.index('{', start)
    depth, state, escape = 0, 'code', False
    i = brace
    while i < len(text):
        c, n = text[i], text[i+1:i+2]
        if state == 'line':
            if c == '\n': state = 'code'
        elif state == 'comment':
            if c == '*' and n == '/': state = 'code'; i += 1
        elif state in ('string', 'char'):
            if escape: escape = False
            elif c == '\\': escape = True
            elif c == ('"' if state == 'string' else "'"): state = 'code'
        elif c == '/' and n == '/': state = 'line'; i += 1
        elif c == '/' and n == '*': state = 'comment'; i += 1
        elif c == '"': state = 'string'
        elif c == "'": state = 'char'
        elif c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return text[start:i+1]
        i += 1
    raise AssertionError('unclosed block')

def function(text, name):
    match = re.search(r'(?m)^(?:static )?(?:void|bool|int64_t|struct secondary_ass_sample_snapshot) '
                      + re.escape(name) + r'\(', text)
    assert match, name
    return braced(text, match.start())

snippets = {}
for name in ('secondary_cache_post_cpu_cost', 'secondary_observe_flip_budget',
             'secondary_physical_feedback'):
    snippets[name] = function(vo, name)
for name in ('osd_get_secondary_sample_snapshot', 'osd_anchor_secondary_clock',
             'osd_hold_secondary_sample', 'osd_set_secondary_physical_forecast_time'):
    snippets[name] = function(osd, name)

start = vo.index('        struct secondary_ass_neutral_pose neutral_source =')
end = vo.index('        if (neutral_admitted) {', vo.index('secondary_ass_neutral_pose_clear(', start))
snippets['fresh_admission'] = vo[start:end]
start = end
branch = braced(vo, start)
snippets['fresh_neutral_assignment'] = branch
start = vo.index('        if (!media_anchored && clock_rate > 0')
snippets['original_anchor_unless_already_anchored'] = braced(vo, start)
start = vo.index('        struct secondary_ass_sample_snapshot pose_after =')
end = vo.index('        if (grid_task && grid_task->stage.valid)', start)
snippets['actual_cache_capture'] = vo[start:end]
start = vo.index('        bool early_present = false;', vo.index('int64_t neutral_release'))
end = vo.index('        stats_time_start(in->stats, "video-flip")', start)
snippets['actual_fresh_wait'] = vo[start:end]
start = osd.index('        if (osd->secondary_sample_held) {', osd.index('static struct sub_bitmaps *render_object'))
end = osd.index('        struct mp_ass_pacing_record scope =', start)
snippets['actual_osd_sample_or_hold'] = osd[start:end]

counts = {name: len(re.findall(r'\b'+name+r'\(', vo)) for name in (
    'secondary_ass_neutral_pose_capture', 'secondary_ass_neutral_pose_admit',
    'secondary_ass_neutral_pose_clear', 'secondary_ass_flip_budget_window',
    'secondary_cache_post_cpu_cost', 'secondary_observe_flip_budget',
    'osd_anchor_secondary_clock')}
assert counts == {'secondary_ass_neutral_pose_capture': 1,
    'secondary_ass_neutral_pose_admit': 1, 'secondary_ass_neutral_pose_clear': 2,
    'secondary_ass_flip_budget_window': 2, 'secondary_cache_post_cpu_cost': 4,
    'secondary_observe_flip_budget': 3, 'osd_anchor_secondary_clock': 2}, counts
assert vo.index('osd_anchor_secondary_clock(', start if False else vo.index('int64_t neutral_release')) < vo.index('secondary_ass_neutral_pose_admit(')
assert 'physical_now = mp_time_ns();' in snippets['fresh_admission']
assert snippets['actual_cache_capture'].index('osd_get_secondary_sample_snapshot') < snippets['actual_cache_capture'].index('mp_mutex_lock')
capture_pos = vo.index('struct secondary_ass_sample_snapshot pose_after')
assert vo.rfind('secondary_physical_feedback(', 0, capture_pos) > vo.rfind('get_vsync(vo, &vsync)', 0, capture_pos)

preamble = r'''
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "video/out/secondary_ass_neutral_pose.h"
#include "video/out/secondary_ass_flip_budget.h"
#include "video/out/secondary_ass_presentation.h"
#define MPMAX(a,b) ((a)>(b)?(a):(b))
#define MP_TIME_MS_TO_NS(a) ((int64_t)((a)*1000000))
#define MP_TIME_S_TO_NS(a) ((int64_t)((a)*1000000000))
#define MP_NOPTS_VALUE (-1e100)
#define VO_EVENT_LIVE_RESIZING 1
#define MP_INFO(...) ((void)0)
#define MP_ASS_PACING_PHYSICAL 1
#define MP_ASS_PACING_FLIP_BUDGET 2
struct mp_ass_pacing_record {
    int64_t event_ns; uint64_t vo_seq, draw_seq, frame_id, epoch, generation, flags;
    int64_t v[16];
};
static int64_t fake_now, waited_until, backend_target;
static int anchor_count, hold_count, lock_count, capture_checks, admission_checks;
static int checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; printf("FAIL %d: %s\n", __LINE__, #x); } } while(0)
static int64_t mp_time_ns(void) { return fake_now; }
static void mp_mutex_lock(int *p) { (void)p; lock_count++; }
static void mp_mutex_unlock(int *p) { (void)p; lock_count--; }
static bool mp_ass_pacing_enabled(void *p) { (void)p; return false; }
static void mp_ass_pacing_record(void *g, int k, const struct mp_ass_pacing_record *p) { (void)g;(void)k;(void)p; }
static uint64_t mp_ass_pacing_double_bits(double x) { uint64_t u; memcpy(&u,&x,sizeof u);return u; }
struct osd_state {
    int lock; struct secondary_ass_sampler secondary_sampler;
    struct secondary_ass_clock secondary_clock;
    bool secondary_sample_held, secondary_has_output, secondary_physical_phase;
    bool secondary_display_forecast, secondary_forecast_forced_sample, secondary_clock_trace;
    double secondary_rate, secondary_speed, secondary_requested_speed;
    uint64_t secondary_physical_epoch;
    int64_t secondary_logical_slot, secondary_target_slot, secondary_phase_wall;
    int64_t secondary_phase_slot, secondary_present_wall, secondary_submit_wall, secondary_vsync_interval;
};
struct image { double pts; };
struct vo_frame { uint64_t frame_id; bool display_synced,repeat,still; int64_t pts; double ideal_frame_vsync; struct image *current; };
struct vo_vsync_info {
    int64_t vsync_duration, secondary_sync_qpc_ns, secondary_sync_time, secondary_display_time;
    uint64_t secondary_submit_id, secondary_submit_generation, secondary_present_id;
    bool secondary_phase_reset, secondary_submit_valid;
    int secondary_submit_sync_interval;
    uint32_t secondary_sync_refresh_count, secondary_present_refresh_count;
};
struct vo;
struct driver { bool (*can_present_early)(struct vo *,uint64_t,int64_t,void (*)(struct vo *,int64_t)); };
struct vo_internal {
    int lock; struct secondary_ass_physical secondary_physical;
    struct secondary_ass_flip_budget secondary_flip_budget;
    struct secondary_ass_neutral_pose secondary_neutral_pose;
    bool secondary_split_budget, secondary_fixed_forecast, secondary_queue_stage, secondary_queue_lead;
    bool paused,send_reset,dropped_frame,visible,secondary_fifo_present,secondary_display_forecast,secondary_trace;
    unsigned queued_events;
    int64_t secondary_render_cost,secondary_redraw_cost,secondary_redraw_block_cost;
    double reported_display_fps;
    struct vo_frame *current_frame,*frame_queued;
};
struct vo { struct vo_internal *in; struct osd_state *osd; struct driver *driver; void *global;
    uint64_t pacing_vo_seq,pacing_draw_seq,pacing_frame_id; };
struct secondary_ass_grid_task { uint64_t current_id, queued_id; };
static void wait_until(struct vo *vo,int64_t t) { (void)vo; waited_until=t; if(t>fake_now)fake_now=t; }
static void secondary_plan_wait_until(struct vo *vo,int64_t t) { wait_until(vo,t); }
static bool backend_ok = true;
static bool endpoint_can_present_early(struct vo *vo,uint64_t g,int64_t t,void (*wait)(struct vo *,int64_t)) {
    (void)vo;(void)g;(void)wait;backend_target=t;return backend_ok;
}
static struct secondary_ass_present_plan secondary_forecast_plan(struct vo *vo,
    struct secondary_ass_physical_point point,int64_t divisor,double rate) {
    (void)divisor;(void)rate;
    return secondary_ass_present_plan_make_fixed_forecast(&vo->in->secondary_physical,point,0);
}
'''

wrappers = r'''
static void capture_caller(struct vo *vo, struct secondary_ass_grid_task *grid_task,
    struct secondary_ass_present_plan present_plan,struct secondary_ass_sample_snapshot stage_before,
    struct vo_vsync_info vsync,bool secondary_target_updated) {
    struct vo_internal *in=vo->in;
    // Same root call order: actual feedback registers before actual capture block.
    secondary_physical_feedback(vo,&vsync,present_plan.target,&present_plan);
    @CAPTURE@
}
struct decision { bool admitted, anchored; struct secondary_ass_present_plan plan; int64_t target, next_prepare; };
static struct decision admission_caller(struct vo *vo,struct vo_frame *frame) {
    struct vo_internal *in=vo->in;
    double clock_rate=72,native_rate=72;
    bool planned_audio=true,physical_phase=false,secondary_target_updated=false; struct secondary_ass_physical_point physical_point={0};
    struct secondary_ass_present_plan early_plan={0},present_plan={0};
    struct secondary_ass_sample_snapshot initial=osd_get_secondary_sample_snapshot(vo->osd);
    int64_t sample_divisor=initial.divisor;
    struct secondary_ass_physical_point native_point=secondary_ass_physical_point_at(&in->secondary_physical,initial.next_slot);
    int64_t original_video_target=frame->pts,target=frame->pts,presentation_time=0;
    int64_t physical_now=mp_time_ns();
    @ADMISSION@
    @NEUTRAL_ASSIGNMENT@
    @ORIGINAL_ANCHOR@
    if(neutral_admitted) { hold_count++; osd_hold_secondary_sample(vo->osd); }
    @WAIT@
    return (struct decision){neutral_admitted,media_anchored,present_plan,target,
        neutral_next.submit-in->secondary_redraw_cost};
}
static double sample_render_caller(struct osd_state *osd) {
    bool changed_sample=false;double video_pts=-100;
    @OSD_SAMPLE@
    return video_pts;
}
'''
for key, label in [('actual_cache_capture','CAPTURE'),('fresh_admission','ADMISSION'),
                   ('fresh_neutral_assignment','NEUTRAL_ASSIGNMENT'),
                   ('original_anchor_unless_already_anchored','ORIGINAL_ANCHOR'),
                   ('actual_fresh_wait','WAIT'),('actual_osd_sample_or_hold','OSD_SAMPLE')]:
    wrappers = wrappers.replace('@'+label+'@',snippets[key])

tests = r'''
struct fixture {
    struct vo vo;struct vo_internal in;struct osd_state osd;struct driver driver;
    struct vo_frame current,queued,frame;struct image image;
    struct secondary_ass_grid_task task;
    struct secondary_ass_present_plan plan;
    struct secondary_ass_sample_snapshot before;
    struct vo_vsync_info vsync;
};
static void init(struct fixture *f) {
    memset(f,0,sizeof *f);int64_t t=6944444,phase=1000000000;
    fake_now=phase+28000000;waited_until=backend_target=0;backend_ok=true;
    anchor_count=hold_count=lock_count=0;
    f->vo.in=&f->in;f->vo.osd=&f->osd;f->vo.driver=&f->driver;
    f->driver.can_present_early=endpoint_can_present_early;
    f->in.secondary_split_budget=f->in.secondary_fixed_forecast=f->in.visible=true;
    f->in.secondary_render_cost=200000;f->in.secondary_redraw_cost=500000;
    f->in.current_frame=&f->current;f->in.frame_queued=&f->queued;
    f->current.frame_id=1000;f->queued.frame_id=1001;
    f->task=(struct secondary_ass_grid_task){1000,1001};
    f->in.reported_display_fps=144;
    f->in.secondary_physical=(struct secondary_ass_physical){
        .phase=phase,.interval=t,.epoch=1,.phase_slot=100,.sync_slot=100,
        .sync_qpc_ns=phase,.sync_segment_consistent=true,.historical_id=9,
        .last_submit_id=9,.success_first_id=9,.success_last_id=9,
        .success_generation=7,.success_contiguous=true,.last_base_slot=102,
        .last_base=phase+2*t,
    };
    f->plan=secondary_ass_present_plan_make_fixed_forecast(&f->in.secondary_physical,
        (struct secondary_ass_physical_point){104,phase+4*t},0);
    CHECK(f->plan.valid);
    f->osd.secondary_rate=72;f->osd.secondary_speed=f->osd.secondary_requested_speed=1;
    f->osd.secondary_has_output=f->osd.secondary_physical_phase=f->osd.secondary_display_forecast=true;
    f->osd.secondary_physical_epoch=1;
    f->osd.secondary_clock=(struct secondary_ass_clock){.valid=true,.speed=1,.pts=730,.wall=phase};
    f->osd.secondary_sampler=(struct secondary_ass_sampler){
        .valid=true,.rate=72,.pts=730+4*t*1e-9,.origin_wall=phase,.sample_wall=phase+4*t,
        .tick=2,.physical_slots=true,.display_forecast=true,.epoch=1,.origin_slot=100,
        .divisor=2,.display_slot=104,.phase_wall=phase,.phase_slot=100,.physical_interval=t,
    };
    f->before=osd_get_secondary_sample_snapshot(&f->osd);
    f->before.sample_slot=102;f->before.next_slot=104;f->before.next_wall=phase+4*t;
    f->vsync=(struct vo_vsync_info){.secondary_submit_valid=true,.secondary_submit_id=10,
        .secondary_submit_generation=7,.secondary_submit_sync_interval=1,
        .secondary_sync_qpc_ns=phase,.secondary_sync_time=phase,.secondary_present_id=9};
    f->image.pts=730+.030;
    f->frame=(struct vo_frame){.frame_id=1001,.pts=phase+30000000,.current=&f->image};
    f->in.secondary_flip_budget=(struct secondary_ass_flip_budget){.epoch=1,.generation=7,
        .last_id=10,.cost=200000,.samples={.count=1}};
}
static void capture(struct fixture *f) {
    capture_caller(&f->vo,&f->task,f->plan,f->before,f->vsync,true);
}
int main(void) {
    struct fixture f;init(&f);capture(&f);
    CHECK(f.in.secondary_neutral_pose.valid);
    CHECK(f.in.secondary_physical.last_base_slot==104);
    uint64_t old_tick=f.osd.secondary_sampler.tick;
    double old_pts=f.osd.secondary_sampler.pts;
    struct decision d=admission_caller(&f.vo,&f.frame);
    CHECK(d.admitted && d.anchored);
    CHECK(!f.in.secondary_neutral_pose.valid);
    CHECK(f.osd.secondary_sample_held);
    CHECK(d.target==f.frame.pts && waited_until==f.frame.pts && backend_target==f.frame.pts);
    CHECK(!d.plan.valid && d.plan.epoch==1 && d.plan.generation==7 && d.plan.base.slot==0 && d.plan.target.slot==0);
    CHECK(f.osd.secondary_sampler.tick==old_tick && sample_render_caller(&f.osd)==old_pts);
    CHECK(fake_now<d.next_prepare && secondary_ass_sampler_next_slot(&f.osd.secondary_sampler)==106);
    int old_h_count=f.in.secondary_physical.delay_count;
    unsigned old_ring=f.in.secondary_physical.next;
    struct vo_vsync_info neutral=f.vsync;neutral.secondary_submit_id=11;
    secondary_physical_feedback(&f.vo,&neutral,(struct secondary_ass_physical_point){0},&d.plan);
    CHECK(f.in.secondary_physical.success_last_id==11 && f.in.secondary_physical.last_submit_id==11);
    CHECK(f.in.secondary_physical.next==old_ring && f.in.secondary_physical.last_base_slot==104);
    CHECK(f.in.secondary_physical.delay_count==old_h_count);
    int64_t begin=fake_now;fake_now+=200000;
    secondary_observe_flip_budget(&f.vo,&neutral,&d.plan,begin,0,begin,true,true,true);
    CHECK(f.in.secondary_flip_budget.last_id==11 && f.in.secondary_flip_budget.samples.count>0);
    CHECK(secondary_cache_post_cpu_cost(&f.vo,true)>0);
    struct secondary_ass_physical *p=&f.in.secondary_physical;
    struct secondary_ass_physical_point next=secondary_ass_physical_point_at(p,106);
    CHECK(osd_set_secondary_physical_forecast_time(&f.osd,next.wall,106,106,p->phase,
        p->phase_slot,p->interval,p->epoch,next.wall-p->interval+1000000));
    CHECK(!f.osd.secondary_sample_held);
    CHECK(sample_render_caller(&f.osd)>old_pts);
    CHECK(f.osd.secondary_sampler.tick==old_tick+1 && secondary_ass_sampler_next_slot(&f.osd.secondary_sampler)==108);
    CHECK(lock_count==0);

#define BAD_CAPTURE(mutate) do { init(&f);capture(&f);CHECK(f.in.secondary_neutral_pose.valid);mutate;capture(&f);CHECK(!f.in.secondary_neutral_pose.valid); } while(0)
    BAD_CAPTURE(f.vsync.secondary_submit_valid=false);
    BAD_CAPTURE(f.current.frame_id++);
    BAD_CAPTURE(f.queued.frame_id++);
    BAD_CAPTURE(f.in.paused=true);
    BAD_CAPTURE(f.in.send_reset=true);
    BAD_CAPTURE(f.in.queued_events=VO_EVENT_LIVE_RESIZING);
    BAD_CAPTURE(f.osd.secondary_sampler.force=true);
    BAD_CAPTURE(f.vsync.secondary_phase_reset=true);
    BAD_CAPTURE(f.vsync.secondary_submit_generation=8);
    init(&f);capture(&f);CHECK(f.in.secondary_neutral_pose.valid);
    capture_caller(&f.vo,NULL,(struct secondary_ass_present_plan){0},f.before,f.vsync,false);
    CHECK(!f.in.secondary_neutral_pose.valid);

    init(&f);capture(&f);f.image.pts+=1.0;
    d=admission_caller(&f.vo,&f.frame);
    CHECK(!d.admitted && d.anchored && !f.osd.secondary_sampler.valid);
    CHECK(!f.in.secondary_neutral_pose.valid && hold_count==0);
    CHECK(f.osd.secondary_clock.pts==f.image.pts);
    init(&f);capture(&f);f.osd.secondary_sampler.force=true;
    d=admission_caller(&f.vo,&f.frame);CHECK(!d.admitted && hold_count==0);
    init(&f);capture(&f);f.frame.pts=1040000000;f.image.pts=730+.04;
    d=admission_caller(&f.vo,&f.frame);CHECK(!d.admitted && hold_count==0);
    init(&f);capture(&f);backend_ok=false;
    d=admission_caller(&f.vo,&f.frame);
    CHECK(d.admitted && waited_until==f.frame.pts);
    begin=fake_now;fake_now+=200000;neutral=f.vsync;neutral.secondary_submit_id=11;
    secondary_physical_feedback(&f.vo,&neutral,(struct secondary_ass_physical_point){0},&d.plan);
    secondary_observe_flip_budget(&f.vo,&neutral,&d.plan,begin,0,begin,false,true,true);
    CHECK(f.in.secondary_flip_budget.samples.count==0 && secondary_cache_post_cpu_cost(&f.vo,true)==0);

#define BAD_Q(mutate) do { init(&f);capture(&f);d=admission_caller(&f.vo,&f.frame);CHECK(d.admitted);neutral=f.vsync;neutral.secondary_submit_id=11;secondary_physical_feedback(&f.vo,&neutral,(struct secondary_ass_physical_point){0},&d.plan);mutate;begin=fake_now;fake_now+=200000;secondary_observe_flip_budget(&f.vo,&neutral,&d.plan,begin,0,begin,true,true,true);CHECK(!f.in.secondary_flip_budget.samples.count); } while(0)
    BAD_Q(neutral.secondary_submit_valid=false);
    BAD_Q(neutral.secondary_phase_reset=true);
    BAD_Q(neutral.secondary_submit_generation=8);
    BAD_Q(neutral.secondary_submit_sync_interval=0);
    BAD_Q(f.in.secondary_physical.outlier_pending=true);
    BAD_Q(f.in.secondary_physical.history_floor_slot=100);
    BAD_Q(f.in.secondary_physical.success_last_id=12);
    BAD_Q(f.in.secondary_physical.success_contiguous=false);
    CHECK(lock_count==0);
    printf("{\"checks\":%d,\"failures\":%d,\"GPU_started\":false,\"core_compiled\":false}\n",checks,failures);
    return failures?7:0;
}
'''

# Anchor execution count is an endpoint observation inserted around the actual
# function call, not a substitute anchor/learner implementation.
for key in ('fresh_admission','original_anchor_unless_already_anchored'):
    pass
source = preamble + '\n'.join(snippets[n] for n in (
    'osd_get_secondary_sample_snapshot','osd_anchor_secondary_clock','osd_hold_secondary_sample',
    'osd_set_secondary_physical_forecast_time','secondary_cache_post_cpu_cost',
    'secondary_observe_flip_budget','secondary_physical_feedback')) + wrappers + tests
out = HERE/'caller-fragments-generated-fix1.c'
assert not out.exists()
out.write_text(source,encoding='utf-8')
results=[]
for flags in ([], ['-DNDEBUG']):
    exe = HERE/('caller-'+('NDEBUG' if flags else 'normal'))
    if compiler_kind == 'TCC':
        cmd=[str(CC),*flags,'-I'+str(CORE),'-run',str(out)]
        r=subprocess.run(cmd,cwd=HERE,capture_output=True,text=True,timeout=30)
    else:
        cmd=[str(CC),'-std=c99','-O2',*flags,'-I'+str(CORE),str(out),'-lm','-o',str(exe)]
        compiled=subprocess.run(cmd,cwd=HERE,capture_output=True,text=True,timeout=30)
        if compiled.returncode:
            r=compiled
        else:
            r=subprocess.run([str(exe)],cwd=HERE,capture_output=True,text=True,timeout=30)
    value={'command':cmd,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if r.returncode==0: value['result']=json.loads(r.stdout)
    results.append(value)
    if r.returncode: break
stable = all(sha(Path(p))==h for p,h in inputs.items())
passed = stable and len(results)==2 and all(r['exit_code']==0 and r['result']=={'checks':86,'failures':0,'GPU_started':False,'core_compiled':False} for r in results)
report={'status':'PASS_CPU_ACTUAL_CALLER_FRAGMENTS_NOT_CORE_NOT_DISPLAY' if passed else 'FAIL_RETAINED',
    'source_hashes':inputs,'source_stable':stable,'callsite_counts_including_definitions':counts,
    'snippet_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in snippets.items()},
    'generated_c_sha256':sha(out),'runner_sha256':sha(Path(__file__)),'compiler_sha256':sha(CC),'compiler_kind':compiler_kind,
    'runs':results,'core_compiled':False,'GPU_started':False,'pacing_acceptance':False,
    'verified':['actual nonnull invalid-plan feedback preserves FIFO without registering neutral G/D into H',
        'actual capture caller uses post-get_vsync registered ID, exact frame owner and sampler checks',
        'actual fresh media anchor is applied before admission and original call is skipped when already anchored',
        'actual neutral wait arms original F, holds one submitted pose and does not consume next G',
        'actual following OSD forecast updates exactly next logical tick after held pose',
        'actual neutral Q cost requires successful same-prefix Sync1/guard and resets on failure/lifecycle/outlier'],
    'unknown':['full VO GCC/Windows build and complete scheduler execution',
        'real OSD mutex contention and concurrent lifecycle/control changes',
        'backend D3D11 lifecycle guard implementation is an explicit endpoint here',
        'actual CPU tails/GPU Ready/PresentMon Display and cross-device pacing']}
REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'report_sha256':sha(REPORT),'runs':results},ensure_ascii=False))
raise SystemExit(0 if passed else 1)
