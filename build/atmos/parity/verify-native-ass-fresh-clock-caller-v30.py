# V30 provider binding; original tests and fault assertions remain unchanged.
#!/usr/bin/env python3
"""CPU gate for real fresh-clock caller selection and preserved video waits.

Uses the frozen actual-declaration/caller builder, never synthesized mpv ABI.
This tool never starts mpv, GPU, CI, or a Display acceptance test.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CALLER_SHA = '8b51405dceb018d4289daaf8036acf38e67599fe687721f221293c391e4f1e7c'
GATE_SHA = '1ea97f67d80f04ed84bc6f299d16988aaeb90820295fec04d9868e5442011d30'
BASELINE_VO_SHA = 'e4e7bd710c84c43af548a66e8950cfb69814db478a4a889239572d3292bafefd'
EXPECTED_NEW_CHECKS = 5109078
TESTS = r'''
static unsigned v28_checks,v28_positive_plans,v28_matrix_cases,v28_model_draws;
static void v28_setup(struct vo *vo,struct vo_internal *in,struct vo_frame *frame,
 struct vo_driver *driver,struct mp_vo_opts *opts,int hz,int fps) {
 setup(vo,in,frame,driver,opts);
 const int64_t T=1000000000LL/hz,O=1000000000;
 const int64_t N=(hz+119)/120;
 fixture_divisor=N;fixture_rate=1e9/(N*(double)T);
 in->secondary_queue_stage=false;in->secondary_display_forecast=true;
 in->secondary_fixed_forecast=true;in->secondary_render_cost=3974400;
 in->secondary_redraw_cost=14742100;in->secondary_redraw_block_cost=15058200;
 in->vsync_interval=T;in->reported_display_fps=1e9/T;
 frame->duration=1000000000LL/fps;
 in->secondary_physical=(struct secondary_ass_physical){.phase=O,.phase_slot=100,
  .interval=T,.epoch=7,.sync_qpc_ns=O,.sync_count=100,.sync_slot=100,
  .sync_segment_consistent=true,.measure_qpc_ns=O,.measure_count=100,
  .periods={T,T,T},.period_count=3,.period_next=3,.delay=1,
  .delay_samples={1,1,1},.delay_count=3,.success_generation=3,.success_contiguous=true};
 fixture_clock=(struct secondary_ass_clock){.valid=true,.pts=10,.speed=1,.wall=O};
 fixture_live_sampler=true;
 struct secondary_ass_present_plan seed=secondary_forecast_plan(vo,
  secondary_ass_physical_point_at(&in->secondary_physical,110),N,fixture_rate);
 CHECK(seed.valid && actual_sampler_selection(in,&seed));
 in->secondary_physical.last_base_slot=seed.base.slot;
 in->secondary_sync_mode_valid=true;in->secondary_sync_mode=false;
 clock_ns=seed.target.wall+10000;
}
static void v28_basic_pressure(int64_t redraw,int64_t stale_for) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
 struct secondary_ass_physical saved=in.secondary_physical;
 int offset=in.secondary_fixed_offset.offset;
 in.secondary_redraw_cost=redraw;
 clock_ns+=stale_for;
 int64_t F=clock_ns+in.secondary_render_cost;
 frame.pts=F;
 struct secondary_ass_present_plan early={0};
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 CHECK(!secondary_ass_budget_affordable(in.secondary_render_cost,redraw,
  frame.duration,fixture_divisor*in.secondary_physical.interval));
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(r.plan.valid && r.plan.fresh_clock_only && r.plan.display_forecast);
 CHECK(r.physical && r.point.slot==r.plan.target.slot && r.point.wall==r.plan.target.wall);
 CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
 CHECK(r.plan.target.wall>F && r.plan.target.slot-r.plan.base.slot==offset);
 CHECK((r.plan.base.slot-native.slot)%fixture_divisor==0);
 CHECK(r.plan.base.slot>saved.last_base_slot);
 CHECK(!memcmp(&saved,&in.secondary_physical,sizeof(saved)));
 CHECK(in.secondary_fixed_offset.offset==offset);
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(&vo,&frame,&r);
 CHECK(fixture_wait_calls==1 && fixture_plan_wait_calls==0 && fixture_wait_target==F);
 driver.can_present_early=NULL;
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(&vo,&frame,&r);
 CHECK(fixture_wait_calls==0 && fixture_plan_wait_calls==1 && fixture_wait_target==F);
 CHECK(actual_sampler_selection(&in,&r.plan));
 CHECK(fixture_sampler.pts>10 && fixture_sampler.physical_slots && fixture_sampler.display_forecast);
 v28_positive_plans++;
 fixture_live_sampler=false;
}
static void v28_feature_matrix(void) {
 for(unsigned mask=0;mask<16;mask++)for(unsigned zero=0;zero<2;zero++)
 for(unsigned repeat=0;repeat<2;repeat++)for(unsigned early_valid=0;early_valid<2;early_valid++)
 for(unsigned ds=0;ds<2;ds++)for(unsigned queue_stage=0;queue_stage<2;queue_stage++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
  in.secondary_redraw_cost=100000000;
  clock_ns+=1000000000;
  int64_t F=clock_ns+in.secondary_render_cost;frame.pts=F;
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  struct secondary_ass_present_plan early=secondary_forecast_plan(&vo,native,fixture_divisor,fixture_rate);
  CHECK(early.valid);
  early.valid=early_valid;
  struct secondary_ass_present_plan saved=early;
  in.secondary_fixed_forecast=!!(mask&1);in.secondary_display_forecast=!!(mask&2);
  in.secondary_present_grid=!!(mask&4);in.secondary_present_plan=!!(mask&8);
  fixture_divisor=zero?0:2;frame.repeat=repeat;frame.display_synced=ds;
  in.secondary_queue_stage=queue_stage;
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  bool expected=mask==15 && !zero && !repeat && !early_valid && !ds;
  CHECK(r.plan.fresh_clock_only==expected);
  CHECK(r.target==F);
  CHECK(!memcmp(&early,&saved,sizeof(early)));
  CHECK(expected?r.plan.valid:!r.plan.valid);
 }
 fixture_live_sampler=false;
}
static void v28_invalid_helper_and_math(void) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
 struct secondary_ass_physical p=in.secondary_physical;
 struct secondary_ass_physical_point first=secondary_next_sample(&vo,fixture_divisor);
 int offset=in.secondary_fixed_offset.offset;
 for(unsigned fault=0;fault<14;fault++) {
  struct secondary_ass_physical q=p;
  struct secondary_ass_physical_point given=first;
  int changed_offset=offset;
  int64_t divisor=fixture_divisor,ready=2000000000,F=2000000000;
  if(fault==0)given.wall++;
  if(fault==1)changed_offset=-1;
  if(fault==2)divisor=0;
  if(fault==3)ready=0;
  if(fault==4)F=0;
  if(fault==5)q.epoch=0;
  if(fault==6)q.success_generation=0;
  if(fault==7)q.epoch_exhausted=true;
  if(fault==8)q.outlier_pending=true;
  if(fault==9)q.sync_segment_consistent=false;
  if(fault==10)q.success_contiguous=false;
  if(fault==11)given=(struct secondary_ass_physical_point){INT64_MAX,INT64_MAX};
  if(fault==12)divisor=INT64_MAX;
  if(fault==13)ready=F=INT64_MAX;
  struct secondary_ass_physical saved=q;
  struct secondary_ass_present_plan bad=secondary_ass_present_plan_fresh_clock(&q,given,divisor,changed_offset,ready,F);
  CHECK(!bad.valid && bad.fresh_clock_only);
  CHECK(!memcmp(&saved,&q,sizeof(q)));
 }
 for(unsigned mode=0;mode<5;mode++) {
  v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
  struct secondary_ass_present_plan early={0};
  first=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=2000000000;clock_ns=F-3974400;frame.pts=F;
  in.secondary_redraw_cost=100000000;
  if(mode==0)fixture_rate=0;
  if(mode==1)in.secondary_render_cost=-1;
  if(mode==2)in.secondary_physical.phase=0;
  if(mode==3)frame.duration=0;
  if(mode==4)clock_ns=INT64_MAX-in.secondary_render_cost+1;
  struct fresh_clock_boundary_result bad=actual_fresh_selection_boundary(&vo,&frame,F,&early,first);
  CHECK(!bad.plan.valid && !bad.plan.fresh_clock_only && bad.target==F);
 }
 fixture_live_sampler=false;
}
static void v28_no_extra_cache_and_late_miss(void) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
 clock_ns=2000000000;
 in.secondary_next_probe=0;in.secondary_redraw_cost=14742100;
 frame.pts=clock_ns-frame.duration+500000;
 bool manual=true;(void)outer_timer_boundary(&vo,false,false,&manual);
 CHECK(!manual && actual_outer_task.point.slot==0 && !actual_outer_task.plan.valid);
 int64_t F=clock_ns+in.secondary_render_cost;frame.pts=F;
 struct secondary_ass_present_plan early={0};
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(r.plan.valid && r.plan.fresh_clock_only && r.target==F);
 for(unsigned queue_stage=0;queue_stage<2;queue_stage++)for(int edge=-1;edge<=1;edge++) {
  struct secondary_ass_present_plan saved=r.plan;
  recorded=(struct mp_ass_pacing_record){0};
  in.secondary_queue_stage=queue_stage;
  in.secondary_stage_prefix.valid=true;
  clock_ns=r.plan.deadline+edge;
  actual_fresh_late_miss_boundary(&vo,&r.plan);
  CHECK(!memcmp(&saved,&r.plan,sizeof(saved)));
  if(edge<0)CHECK(recorded.v[0]==0 && in.secondary_stage_prefix.valid);
  else {
   CHECK(recorded.v[0]==saved.target.slot && recorded.v[1]==saved.target.wall);
   CHECK(recorded.v[2]==saved.base.slot && recorded.v[3]==saved.base.wall && recorded.v[4]==saved.deadline);
   CHECK(recorded.v[5]==secondary_record_tag("fresh_clock_vo_flip_after_target"));
   CHECK(recorded.v[6]==secondary_record_tag("after-flip"));
   CHECK(recorded.flags==1);
   CHECK(in.secondary_stage_prefix.valid==!queue_stage);
  }
 }
 recorded=(struct mp_ass_pacing_record){0};
 secondary_trace_plan_missed(&vo,"fixed_fifo_after_target","before-draw",&r.plan);
 CHECK(recorded.flags==0 && recorded.v[0]==r.plan.target.slot && recorded.v[1]==r.plan.target.wall);
 fixture_live_sampler=false;
}
static void v28_long_models(void) {
 if(failures)return; // A rejected fault needs no 340200-draw negative replay.
 const int hz_values[]={60,120,144,165,240,360};
 const int fps_values[]={24,25,30,50,60};
 for(unsigned h=0;h<6;h++)for(unsigned f=0;f<5;f++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v28_setup(&vo,&in,&frame,&driver,&opts,hz_values[h],fps_values[f]);
  in.secondary_redraw_cost=100000000;
  struct secondary_ass_physical original=in.secondary_physical;
  struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
  struct secondary_ass_present_plan early={0};
  int64_t origin=fixture_sampler.origin_slot,previous_slot=0;
  double previous_pts=fixture_sampler.pts;
  const int64_t F0=2000000000;
  unsigned count=(unsigned)fps_values[f]*300;
  for(unsigned i=0;i<count;i++) {
   int64_t F=F0+(int64_t)i*1000000000LL/fps_values[f];
   int64_t jitter=i%97==0?100000:i%101==0?-100000:0;
   clock_ns=F-in.secondary_render_cost+jitter;frame.pts=F;
   struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
   struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
   CHECK(r.plan.valid && r.plan.fresh_clock_only && r.physical);
   CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
   CHECK(r.plan.target.wall>MPMAX(F,clock_ns+in.secondary_render_cost));
   CHECK(r.plan.base.slot>previous_slot && (r.plan.base.slot-origin)%fixture_divisor==0);
   CHECK(r.plan.target.slot-r.plan.base.slot==fixed.offset);
   CHECK(!memcmp(&original,&in.secondary_physical,sizeof(original)));
   CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
   CHECK(actual_sampler_selection(&in,&r.plan));
   CHECK(fixture_sampler.pts>previous_pts && fixture_sampler.origin_slot==origin);
   previous_pts=fixture_sampler.pts;previous_slot=r.plan.base.slot;
   v28_model_draws++;
   if(failures)return;
  }
  v28_matrix_cases++;
 }
 fixture_live_sampler=false;
}
static void v28_tests(void) {
 unsigned start=checks;
 v28_basic_pressure(11239000,15419561000LL);
 v28_basic_pressure(14742100,1518247200LL);
 v28_feature_matrix();
 v28_invalid_helper_and_math();
 v28_no_extra_cache_and_late_miss();
 v28_long_models();
 v28_checks=checks-start;
 fprintf(stderr,"V28 fresh clock checks=%u plans=%u matrix=%u draws=%u failures=%u\n",v28_checks,v28_positive_plans,v28_matrix_cases,v28_model_draws,failures);
}
'''


def sha(value):
    return hashlib.sha256(value).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def once(text, before, after, context):
    require(before != after and text.count(before) == 1,
            'Nonunique/unchanged extraction or fault: ' + context)
    return text.replace(before, after, 1)


def actual_multiline_plan_helper(gate, text, name):
    # The frozen builder's function-name scanner does not include a return
    # type placed on its own preceding line. Extend extraction locally using
    # its unchanged literal/comment masker and balanced braces.
    masked = gate.mask_c(text)
    found = list(re.finditer(r'^static\s+inline\s+struct\s+secondary_ass_present_plan\s+' +
                            re.escape(name) + r'\s*\(', masked, re.M))
    require(len(found)==1, 'Unique actual multiline plan helper required: '+name)
    start = found[0].start()
    opening_paren = masked.index('(', start)
    end_paren = gate.balanced(masked, opening_paren, '(', ')')
    opening = end_paren
    while opening<len(masked) and masked[opening].isspace():
        opening+=1
    require(opening<len(masked) and masked[opening]=='{', 'Actual helper body absent')
    end = gate.balanced(masked, opening)
    return text[start:end]


def caller_boundaries(gate, read, generated, report):
    source = read('video/out/vo.c')
    functions = gate.functions(source)
    render = functions['render_frame']['text']
    start = render.index('        int64_t display_interval =')
    end = render.index('        if (!secondary_target_updated && in->secondary_trace)', start)
    selection = render[start:end]
    wait_start = render.index('        bool early_present = false;', end)
    wait_end = render.index('        stats_time_start(in->stats, "video-flip");', wait_start)
    wait = render[wait_start:wait_end]
    report['fresh_selection'] = {'sha256': sha(selection.encode()), 'text': selection}
    # The frozen 76 cases deliberately have no successful neutral lease. Keep
    # all new selection source, but compile media PTS through an explicitly
    # observable scalar endpoint; mp_image layout is not inferred or claimed.
    media_operand = 'frame->current->pts'
    require(selection.count(media_operand) == 1, 'Unique new anchor media operand absent')
    selection = selection.replace(media_operand, 'fixture_media_pts(frame->current)', 1)
    neutral_snapshot = re.search(
        r'\bstruct\s+secondary_ass_sample_snapshot\s+sample\s*=[^;]+;', gate.mask_c(selection))
    require(neutral_snapshot, 'Actual new neutral snapshot statement absent')
    statement = selection[neutral_snapshot.start():neutral_snapshot.end()]
    selection = selection.replace(statement,
        'fixture_v30_new_osd_scope = true;\n' + statement +
        '\nfixture_v30_new_osd_scope = false;', 1)
    report['V30_legacy_selection_boundary'] = {
        'raw_source_sha256': report['fresh_selection']['sha256'],
        'compiled_selection_sha256': sha(selection.encode()),
        'unique_scalar_operand_transform': [media_operand, 'fixture_media_pts(frame->current)'],
        'mp_image_operand_and_layout_compiled': False,
        'neutral_lease_scope': 'INVALID_LEASE_ONLY; separate V30 neutral caller covers admission',
        'extra_OSD_check_counter': 'fixture_v30_new_osd_checks',
        'old_CHECK_assertions_changed': False, 'lock_failure_still_fails': True}

    report['fresh_wait_boundary'] = {'sha256': sha(wait.encode()), 'text': wait}
    flip_match = re.search(r'\bint64_t\s+flip_call\s*=\s*mp_time_ns\(\)\s*;', gate.mask_c(render))
    late_match = re.search(r'\bif\s*\(present_plan\.valid\s*&&\s*present_plan\.fresh_clock_only\s*&&[^;]+;', gate.mask_c(render))
    require(flip_match and late_match, 'Actual flip entry and late MISS boundary absent')
    flip_clock = render[flip_match.start():flip_match.end()]
    late = render[late_match.start():late_match.end()]
    report['fresh_late_miss_boundary'] = {'clock_sha256': sha(flip_clock.encode()),
                                        'sha256': sha(late.encode()), 'text': late}
    report['actual_full_functions_added'] = []
    additional = []
    for name in ('secondary_reset_physical',):
        actual = functions[name]
        require(name not in gate.functions(generated), 'Actual body unexpectedly duplicated: ' + name)
        additional.append('#line ' + str(actual['line']) + ' "video/out/vo.c"\n' + actual['text'])
        report['actual_full_functions_added'].append({'name': name, 'sha256': sha(actual['text'].encode())})
    # Any new VO-local fresh helper is compiled verbatim, rather than replaced
    # by a hand-written direct call to the public inline helper.
    for name, actual in sorted(functions.items(), key=lambda pair: pair[1]['line']):
        if 'fresh_clock' in name and name not in gate.functions(generated):
            additional.append('#line ' + str(actual['line']) + ' "video/out/vo.c"\n' + actual['text'])
            report['actual_full_functions_added'].append({'name': name, 'sha256': sha(actual['text'].encode())})
    endpoint = []
    osd_header = read('sub/osd.h')
    anchor_name = 'osd_anchor_secondary_clock'
    anchor_pattern = r'\bvoid\s+' + anchor_name + r'\s*\([^;{}]*\)\s*;'
    anchors = list(re.finditer(anchor_pattern, gate.mask_c(osd_header)))
    require(len(anchors) == 1, 'Actual OSD anchor signature changed')
    anchor_decl = osd_header[anchors[0].start():anchors[0].end()]
    endpoint.append(anchor_decl[:-1] + '{ (void)osd;(void)pts;(void)wall;(void)display_synced; }')
    report.setdefault('endpoint_signatures', []).append({'name': anchor_name,
        'sha256': sha(anchor_decl.encode()), 'body_executed': False,
        'scope': 'EXTERNAL_FIXTURE_REAL_SIGNATURE_LEGACY_INVALID_LEASE_DOES_NOT_CALL'})
    for name, counter in (('wait_until', 'fixture_wait_calls'),
                          ('secondary_plan_wait_until', 'fixture_plan_wait_calls')):
        actual = functions[name]
        signature = actual['text'][:gate.mask_c(actual['text']).index('{')]
        args = re.search(r'\(\s*struct vo \*(\w+)\s*,\s*int64_t (\w+)\s*\)', signature)
        require(args, 'Actual wait endpoint signature changed: ' + name)
        endpoint.append(signature + '{ (void)' + args[1] + ';' + counter + '++;fixture_wait_target=' + args[2] + '; }')
        report.setdefault('endpoint_signatures', []).append({'name': name, 'sha256': sha(signature.encode()),
            'body_executed': False, 'observable_wait_target': True})
    wrappers = r'''
static unsigned fixture_wait_calls,fixture_plan_wait_calls;
static int64_t fixture_wait_target;
static unsigned fixture_v30_media_operand_reads;
static double fixture_media_pts(const struct mp_image *image) {
 (void)image;fixture_v30_media_operand_reads++;return 0;
}
''' + '\n'.join(endpoint) + '\n' + '\n'.join(additional) + r'''
struct fresh_clock_boundary_result {
 struct secondary_ass_present_plan plan;
 struct secondary_ass_physical_point point;
 int64_t target,present_ready,presentation_time,display_interval;
 bool physical,planned_audio,updated;
};
static struct fresh_clock_boundary_result actual_fresh_selection_boundary(
 struct vo *vo,struct vo_frame *frame,int64_t original_video_target,
 const struct secondary_ass_present_plan *early,
 struct secondary_ass_physical_point native_point) {
 struct vo_internal *in=vo->in;
 // This provider executes only the unchanged old zero-lease test scope.
 if(in->secondary_neutral_pose.valid) {
  failures++;fprintf(stderr,"check failed: legacy scope has neutral lease\n");
  return (struct fresh_clock_boundary_result){0};
 }
 struct secondary_ass_present_plan early_plan=*early;
 struct secondary_ass_sample_snapshot queue_sample=osd_get_secondary_sample_snapshot(vo->osd);
 double native_rate=osd_get_secondary_refresh(vo->osd);
 int64_t sample_divisor=osd_get_secondary_physical_sample_divisor(vo->osd);
 int64_t duration=frame->duration,target=original_video_target;
''' + selection + r'''
 return (struct fresh_clock_boundary_result){present_plan,physical_point,target,present_ready,
  presentation_time,display_interval,physical_phase,planned_audio,secondary_target_updated};
}
static void actual_fresh_wait_boundary(struct vo *vo,struct vo_frame *frame,
 const struct fresh_clock_boundary_result *input) {
 struct vo_internal *in=vo->in;
 struct secondary_ass_present_plan present_plan=input->plan;
 struct secondary_ass_physical_point physical_point=input->point;
 int64_t target=input->target;
 int64_t original_video_target=input->target; // Neutral disabled in legacy wait scope.
 bool physical_phase=input->physical,planned_audio=input->planned_audio;
 bool secondary_target_updated=input->updated;
 bool neutral_admitted=false; // Legacy tests have no successful neutral lease.
''' + wait + r'''
}
static void actual_fresh_late_miss_boundary(struct vo *vo,
 const struct secondary_ass_present_plan *input) {
 struct secondary_ass_present_plan present_plan=*input;
''' + flip_clock + '\n' + late + r'''
}
'''
    marker = 'struct pressure_result {'
    require(generated.count(marker) == 1, 'Frozen fixture insertion boundary changed')
    return generated.replace(marker, wrappers + '\n' + marker, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--parity', type=Path, default=HERE,
                        help='Directory containing frozen V26 builders; default is tool directory')
    parser.add_argument('--inspect-only', action='store_true',
                        help='Write the real boundary translation; explicitly no compile/pass claim')
    args = parser.parse_args()
    source, baseline, parity = args.source.resolve(), args.baseline.resolve(), args.parity.resolve()
    compiler = shutil.which(args.cc)
    require(compiler, 'Compiler not found')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    caller_path = parity / 'verify-native-ass-queue-stage-caller-v30.py'
    gate_path = parity / 'verify-native-ass-integration-v30.py'
    require(sha(caller_path.read_bytes()) == CALLER_SHA, 'Frozen caller builder changed')
    require(sha(gate_path.read_bytes()) == GATE_SHA, 'Frozen declaration gate changed')
    old_bytes = (baseline / 'video/out/vo.c').read_bytes()
    require(sha(old_bytes) == BASELINE_VO_SHA, 'Strict V22 baseline changed')
    captured = {}

    def read(path):
        if path not in captured:
            captured[path] = (source / path).read_bytes()
        return captured[path].decode('utf-8')

    caller = load('fresh_clock_frozen_caller', caller_path)
    caller.ROOT, caller.BASELINE, caller.GATE, caller.CC = source, baseline, gate_path, Path(compiler).resolve()
    gate = caller.load_gate()
    report = {'status': 'ACTUAL_FRESH_CLOCK_BOUNDARY_PREPARING_NOT_RUNTIME',
              'tool_sha256': sha(Path(__file__).read_bytes()), 'caller_sha256': CALLER_SHA,
              'declaration_gate_sha256': GATE_SHA, 'baseline_vo_sha256': BASELINE_VO_SHA,
              'GPU_started': False, 'CI_started': False, 'Display_acceptance': False,
              'pacing_acceptance': False, 'source_root': str(source), 'cases': {},
              'boundary_stubs': ['Windows endpoints with actual declarations/lock wrappers',
                                 'Observable OSD setter with actual prototype; actual forecast sampler run separately',
                                 'Observable platform wait endpoints with actual signatures',
                                 'Logging, pacing sink and talloc endpoints'],
              'long_model_scope': '30 fixed external physical-phase models, 300 seconds per Hz/fps pair; actual VO selection and sampler code, no backend/Present/Display feedback invented',
              'not_covered': ['Full VO loop, full Atomic OSD producer, Windows ABI',
                              'GPU completion, Present-entry timing, actual Display pacing or flicker acceptance']}
    report['expected_counts'] = {'old_checks': 103149, 'old_fixed_checks': 1097,
                                 'old_feedback_frames': 312, 'old_early_prepare_positive': 12,
                                 'new_checks': EXPECTED_NEW_CHECKS, 'new_plans': 2,
                                 'matrix_cases': 30, 'model_draws': 340200,
                                 'normal_and_NDEBUG_modes': 2, 'faults': 15, 'exact_cases': 32}
    report['negative_replay_boundary'] = 'Old CHECK prints at most 20 failures; the long model exits when a fault is already rejected. Full 30x300-second model is required for both positives.'
    passed = False
    try:
        generated, report['frozen_builder_evidence'] = caller.build(gate, read, old_bytes.decode('utf-8'))
        generated = caller_boundaries(gate, read, generated, report)
        cpath = output / 'actual-fresh-boundary.c'
        cpath.write_text(generated, encoding='utf-8', newline='\n')
        report['translation_sha256'] = sha(generated.encode())
        if args.inspect_only:
            report['status'] = 'ACTUAL_FRESH_CLOCK_BOUNDARY_EXTRACTED_NOT_COMPILED'
        else:
            require('secondary_ass_present_plan_fresh_clock' in read('video/out/secondary_ass_present_plan.h'),
                    'Actual V28 fresh-clock helper not available yet')
            generated = once(generated, 'int main(void) {', TESTS + '\nint main(void) {', 'new cases')
            generated = once(generated, ' return failures ? 7 : 0;\n}',
                             ' v28_tests();\n return failures ? 7 : 0;\n}', 'execute new cases after frozen counters')
            report['translation_sha256'] = sha(generated.encode())
            variants = {'positive': generated}

            def fault(name, function, before, after):
                actual = gate.functions(generated)[function]['text']
                if name in ('feature_scope_lost', 'repeat_scope_lost', 'captured_early_scope_lost'):
                    # New neutral eligibility contains similar tokens; mutate
                    # the exact unchanged old fresh-clock eligibility only.
                    old_scope = re.search(r'\bbool\s+fresh_clock_only\s*=[^;]+;', actual).group()
                    changed_scope = once(old_scope, before, after, name + ' original eligibility')
                    changed = once(actual, old_scope, changed_scope, name + ' bound eligibility')
                elif name == 'ready_overflow_guard_lost':
                    old_scope_start = actual.index('} else if (physical_phase &&')
                    old_scope_end = actual.index('{', old_scope_start)
                    old_scope = actual[old_scope_start:old_scope_end]
                    changed = once(actual, old_scope, once(old_scope, before, after,
                        name + ' original fresh guard'), name + ' bound fresh guard')
                else:
                    changed = once(actual, before, after, name)
                variants[name] = once(generated, actual, changed, name + ' function')

            selection = gate.functions(generated)['actual_fresh_selection_boundary']['text']
            eligibility = re.search(r'\bbool\s+fresh_clock_only\s*=[^;]+;', selection).group()
            fault('fresh_eligibility_omitted', 'actual_fresh_selection_boundary', eligibility, 'bool fresh_clock_only = false;')
            fault('feature_scope_lost', 'actual_fresh_selection_boundary',
                  'secondary_forecast_enabled(vo, frame->display_synced, sample_divisor) &&', 'true &&')
            fault('repeat_scope_lost', 'actual_fresh_selection_boundary', '!frame->repeat &&', 'true &&')
            fault('captured_early_scope_lost', 'actual_fresh_selection_boundary', '!early_plan.valid &&', 'true &&')
            fault('ready_overflow_guard_lost', 'actual_fresh_selection_boundary',
                  'physical_now <= INT64_MAX - in->secondary_render_cost', 'true')
            fault('video_target_retimed_to_D', 'actual_fresh_selection_boundary',
                  'target = present_plan.fresh_clock_only ? original_video_target : submit;',
                  'target = present_plan.fresh_clock_only ? present_plan.target.wall : submit;')
            fault('late_equality_omitted', 'actual_fresh_late_miss_boundary',
                  'flip_call >= present_plan.deadline', 'flip_call > present_plan.deadline')
            fault('after_flip_actual_draw_bit_lost', 'secondary_trace_plan_missed',
                  '.flags = (uint64_t)actual_draw,', '.flags = 0,')
            fault('late_captured_D_renamed', 'secondary_trace_plan_missed',
                  '.v = {plan->target.slot, plan->target.wall, plan->base.slot,',
                  '.v = {plan->target.slot, mp_time_ns(), plan->base.slot,')
            plan_path = 'video/out/secondary_ass_present_plan.h'
            plan_header = read(plan_path)
            helper = actual_multiline_plan_helper(gate, plan_header, 'secondary_ass_present_plan_fresh_clock')
            report['actual_helper_sha256'] = sha(helper.encode())
            header_faults = {
                'plan_submit_retained_D': once(helper, 'plan.submit = video_submit;', 'plan.submit = plan.target.wall;', 'submit F lost'),
                'fallback_retained_D': once(helper, 'plan.fallback_submit = video_submit;', 'plan.fallback_submit = plan.target.wall;', 'fallback F lost'),
                'lifecycle_wait_retained_D': once(helper, 'plan.lifecycle_safe_wait = video_submit;', 'plan.lifecycle_safe_wait = plan.target.wall;', 'lifecycle F lost'),
                'divided_lattice_lost': once(helper, 'divisor, after, offset', '1, after, offset', 'lattice divisor lost'),
                'physical_phase_mutated': once(helper, 'plan.submit = video_submit;',
                    '((struct secondary_ass_physical *)p)->phase++;\n    plan.submit = video_submit;', 'phase mutated'),
                'historical_H_mutated': once(helper, 'plan.submit = video_submit;',
                    '((struct secondary_ass_physical *)p)->delay++;\n    plan.submit = video_submit;', 'H mutated'),
            }

            def execute(name, code, mode, flags, negative, include=source):
                cpath = output / (name + '.c')
                if not cpath.exists():
                    cpath.write_text(code, encoding='utf-8', newline='\n')
                else:
                    require(cpath.read_bytes()==code.encode(), 'Existing C evidence changed')
                caller.ROOT = include
                execution = caller.execute_c(cpath, flags)
                caller.ROOT = source
                result = json.loads(execution['stdout']) if execution['stdout'].strip() else {}
                matched = re.search(r'V28 fresh clock checks=(\d+) plans=(\d+) matrix=(\d+) draws=(\d+) failures=(\d+)', execution['stderr'])
                v28_result = {'checks': int(matched[1]), 'plans': int(matched[2]), 'matrix': int(matched[3]),
                              'draws': int(matched[4]), 'failures': int(matched[5])} if matched else {}
                compiled = (execution.get('compiled') is True and execution.get('compile_returncode')==0 or
                            execution.get('compile_and_run') is True and bool(result) and bool(v28_result))
                frozen = (result.get('checks')==103149 and result.get('v24_checks')==1097 and
                          result.get('failures')==0 and result.get('actual_feedback_frames')==312 and
                          result.get('early_prepare_positive')==12)
                if negative:
                    accepted = compiled and frozen and execution['exit_code']==7 and v28_result.get('failures',0)>0
                else:
                    accepted = compiled and frozen and execution['exit_code']==0 and v28_result=={
                        'checks': EXPECTED_NEW_CHECKS, 'plans': 2, 'matrix': 30, 'draws': 340200, 'failures': 0}
                execution.update({'result': result, 'v28_result': v28_result, 'negative': negative,
                                  'compiled_and_expected': accepted, 'translation_sha256': sha(code.encode())})
                report['cases'][name+'_'+mode] = execution
                require(accepted, 'Actual fresh-clock case failed: '+name+'_'+mode+' '+execution['stderr'][-2000:])
                print(json.dumps({'case':name+'_'+mode,'compiled_and_expected':accepted}), flush=True)

            for name, code in variants.items():
                for mode, flags in (('normal', []), ('NDEBUG', ['-DNDEBUG'])):
                    execute(name, code, mode, flags, name!='positive')
            for name, changed in header_faults.items():
                include = output / ('headers-'+name)
                include.mkdir()
                for relative, data in captured.items():
                    if relative.endswith('.h'):
                        dest = include/relative
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(data)
                (include/plan_path).write_text(once(plan_header, helper, changed, name+' header'),
                                              encoding='utf-8', newline='\n')
                for mode, flags in (('normal', []), ('NDEBUG', ['-DNDEBUG'])):
                    execute(name, generated, mode, flags, True, include)
            require(len(report['cases'])==32, 'Positive two modes and 15 faults two modes required')
            require(not any((source/name).read_bytes()!=data for name,data in captured.items()), 'Source changed during execution')
            report['status']='ACTUAL_FRESH_CLOCK_CALLER_CPU_PASS_NOT_RUNTIME'
            passed=True
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        report['status'] = 'ACTUAL_FRESH_CLOCK_CPU_GATE_NOT_READY_OR_FAIL'
        report['error'] = str(error)
    report['source_sha256'] = {name: sha(data) for name, data in captured.items()}
    report['inputs_changed_during_extraction'] = [name for name, data in captured.items()
                                               if (source / name).read_bytes() != data]
    target = output / 'fresh-clock-caller.json'
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(target), 'report_sha256': sha(target.read_bytes())}))
    return 0 if passed or args.inspect_only and report['status'] == 'ACTUAL_FRESH_CLOCK_BOUNDARY_EXTRACTED_NOT_COMPILED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
