#!/usr/bin/env python3
"""Actual V29 fresh retry caller CPU contract; never a Display acceptance.

The frozen V28 declaration/caller builder and all 32 cases remain separate.
Additional tests observe actual source selection and immutable MISS records.
Only platform clock/wait/record sinks are fixtures; no Present/Display is made.
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
V28_SHA = '2b0162b53641d12874be407efa433e3b4f295bb15074821ab85093b64341e750'
EXPECTED_RETRY = {'checks':8441282,'plans':5,'rejected':41,'time_edges':3,
                  'matrix':30,'draws':340200,'failures':0}
EXPECTED_RETRY_FAULT_FAILURES = {
    'retry_omitted':25,'retry_repeat_scope_lost':4,'retry_captured_early_scope_lost':3,
    'retry_queue_stage_scope_lost':4,'retry_fixed_scope_lost':1,'retry_proposal_authority_lost':2,
    'retry_original_MISS_omitted':7,'retry_old_D_renamed':9,'retry_old_G_renamed':9,
    'retry_zero_clock_guard_lost':1,'retry_overflow_guard_lost':1,'retry_ready_not_refreshed':2,
    'retry_submit_retained_D':5,'retry_fallback_retained_D':5,'retry_lifecycle_retained_D':9,
    'retry_deadline_renamed':4,'retry_physical_phase_mutated':13,'retry_historical_H_mutated':5,
    'retry_fixed_offset_mutated':5,'retry_old_task_revived':9,'retry_lattice_divisor_lost':14}
EXPECTED_OLD_FAULT_FAILURES = {
    'fresh_eligibility_omitted':35,'feature_scope_lost':32,'repeat_scope_lost':4,
    'captured_early_scope_lost':4,'ready_overflow_guard_lost':1,'video_target_retimed_to_D':7,
    'late_equality_omitted':11,'after_flip_actual_draw_bit_lost':4,'late_captured_D_renamed':3,
    'plan_submit_retained_D':2,'fallback_retained_D':2,'lifecycle_wait_retained_D':4,
    'divided_lattice_lost':2,'physical_phase_mutated':4,'historical_H_mutated':2}
TESTS = r'''
static unsigned v29_checks,v29_positive_plans,v29_rejected_scopes,v29_time_edges;
static unsigned v29_matrix_cases,v29_model_draws;
static void v29_clear_observation(void) {
 v29_record_count=0;recorded=(struct mp_ass_pacing_record){0};
 v29_clock_advances=false;v29_clock_reads=0;
}
static void v29_setup(struct vo *vo,struct vo_internal *in,struct vo_frame *frame,
 struct vo_driver *driver,struct mp_vo_opts *opts) {
 v28_setup(vo,in,frame,driver,opts,144,50);
 in->secondary_render_cost=1000000;in->secondary_redraw_cost=1000000;
 in->secondary_redraw_block_cost=1000000;
 in->secondary_physical.success_first_id=1;
 in->secondary_physical.historical_id=1;
 in->secondary_physical.success_last_id=2;
 v29_clear_observation();
 CHECK(secondary_ass_budget_affordable(in->secondary_render_cost,
  in->secondary_redraw_cost,frame->duration,fixture_divisor*in->secondary_physical.interval));
}
static void v29_original_miss(const struct secondary_ass_present_plan *old,
 const char *reason) {
 CHECK(v29_record_count==1);
 if(v29_record_count!=1)return;
 CHECK(v29_record_kind[0]==MP_ASS_PACING_MISS);
 const struct mp_ass_pacing_record *m=&v29_records[0];
 CHECK(m->flags==0 && m->epoch==old->epoch && m->generation==old->generation);
 CHECK(m->v[0]==old->target.slot && m->v[1]==old->target.wall);
 CHECK(m->v[2]==old->base.slot && m->v[3]==old->base.wall && m->v[4]==old->deadline);
 CHECK(m->v[5]==secondary_record_tag(reason));
 CHECK(m->v[6]==secondary_record_tag("before-draw"));
}
static void v29_waits(struct vo *vo,struct vo_frame *frame,
 struct vo_driver *driver,const struct fresh_clock_boundary_result *r,int64_t F) {
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(vo,frame,r);
 CHECK(fixture_wait_calls==1 && fixture_plan_wait_calls==0 && fixture_wait_target==F);
 driver->can_present_early=NULL;
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(vo,frame,r);
 CHECK(fixture_wait_calls==0 && fixture_plan_wait_calls==1 && fixture_wait_target==F);
 driver->can_present_early=can_early;
}
// 0: G<F<D, permitting the same G/D on the new uncaptured task.
// 1: authoritative FIFO passed D; 2/3: deadline equality/after equality.
// 4/5: ordinary candidate and D-1 remain the original normal policy.
static void v29_candidate(unsigned mode,unsigned scope) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v29_setup(&vo,&in,&frame,&driver,&opts);
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 struct secondary_ass_physical before_fifo=in.secondary_physical;
 int64_t T=in.secondary_physical.interval,F=native.wall;
 clock_ns=native.wall-in.secondary_render_cost-100000;
 if(mode==0)F=native.wall+T/2;
 if(mode==1) {
  struct secondary_ass_physical_point shifted=secondary_ass_physical_point_at(
   &in.secondary_physical,native.slot-3);
  in.secondary_physical.phase=shifted.wall;
  in.secondary_physical.phase_slot=shifted.slot;
  in.secondary_physical.success_last_id=9;
 }
 struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,
  fixture_divisor,fixture_rate);
 if(mode==2)clock_ns=old.deadline;
 if(mode==3)clock_ns=old.deadline+1;
 if(mode==5)clock_ns=old.deadline-1;
 CHECK(old.target.slot>0 && old.deadline==old.target.wall && old.deadline>0);
 CHECK(mode==1?(!old.valid && old.fifo_lower>old.target.slot):old.valid);
 struct secondary_ass_present_plan early={0};
 if(scope==1)in.secondary_queue_stage=true;
 if(scope==2)early=secondary_ass_present_plan_make_fixed_forecast(&before_fifo,native,
  in.secondary_fixed_offset.offset);
 if(scope==3)frame.repeat=true;
 frame.pts=F;
 struct secondary_ass_present_plan saved_early=early;
 struct secondary_ass_physical physical=in.secondary_physical;
 struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
 struct secondary_ass_sampler sampler=fixture_sampler;
 v29_clear_observation();
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(!memcmp(&early,&saved_early,sizeof(early)));
 CHECK(!memcmp(&physical,&in.secondary_physical,sizeof(physical)));
 CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
 CHECK(!memcmp(&sampler,&fixture_sampler,sizeof(sampler)));
 if(mode<4) {
  if(mode==1 && scope==2) {
   // This already captured early task retains its original proposal even
   // after FIFO advances. Its historical semantics are not changed here.
   CHECK(!v29_record_count && !r.plan.fresh_clock_only);
   CHECK(!memcmp(&r.plan,&saved_early,sizeof(saved_early)) && r.target==saved_early.submit);
   v29_rejected_scopes++;fixture_live_sampler=false;return;
  }
  v29_original_miss(&old,mode==0?"before_video_due":mode==1?"fixed_fifo_after_target":
   "fixed_display_deadline_expired");
  if(scope) {
   CHECK(!r.plan.valid && !r.plan.fresh_clock_only && !r.physical && r.target==F);
   v29_rejected_scopes++;
  } else {
   CHECK(r.plan.valid && r.plan.fresh_clock_only && r.plan.display_forecast && r.physical);
   CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
   CHECK(r.plan.deadline==r.plan.target.wall && r.plan.target.wall>MPMAX(F,clock_ns+in.secondary_render_cost));
   CHECK(r.plan.base.slot>physical.last_base_slot &&
    (r.plan.base.slot-native.slot)%fixture_divisor==0);
   CHECK(r.plan.target.slot-r.plan.base.slot==fixed.offset);
   CHECK(r.plan.epoch==old.epoch && r.plan.generation==old.generation);
   if(mode==0)CHECK(r.plan.base.slot==old.base.slot && r.plan.target.slot==old.target.slot);
   else CHECK(r.plan.base.slot>old.base.slot && r.plan.target.slot>old.target.slot);
   if(mode==1)CHECK(r.plan.fifo_known && r.plan.target.slot>=r.plan.fifo_lower);
   v29_waits(&vo,&frame,&driver,&r,F);
   CHECK(actual_sampler_selection(&in,&r.plan));
   CHECK(fixture_sampler.pts>sampler.pts && fixture_sampler.origin_slot==sampler.origin_slot);
   v29_positive_plans++;
  }
 } else {
  CHECK(!v29_record_count && r.plan.valid && !r.plan.fresh_clock_only);
  CHECK(!memcmp(&r.plan,&old,sizeof(old)) && r.target==old.submit);
 }
 fixture_live_sampler=false;
}
static void v29_feature_and_authority(void) {
 for(unsigned mask=0;mask<15;mask++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=native.wall+in.secondary_physical.interval/2;
  clock_ns=native.wall-in.secondary_render_cost-100000;frame.pts=F;
  in.secondary_fixed_forecast=!!(mask&1);in.secondary_display_forecast=!!(mask&2);
  in.secondary_present_grid=!!(mask&4);in.secondary_present_plan=!!(mask&8);
  struct secondary_ass_present_plan early={0};
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  CHECK(!r.plan.fresh_clock_only);v29_rejected_scopes++;
 }
 for(unsigned fault=0;fault<12;fault++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=native.wall+in.secondary_physical.interval/2;
  clock_ns=native.wall-in.secondary_render_cost-100000;frame.pts=F;
  if(fault==0)fixture_divisor=0;
  if(fault==1)fixture_rate=0;
  if(fault==2)in.secondary_physical.epoch=0;
  if(fault==3)in.secondary_physical.success_generation=0;
  if(fault==4)in.secondary_physical.epoch_exhausted=true;
  if(fault==5)in.secondary_physical.outlier_pending=true;
  if(fault==6)in.secondary_physical.sync_segment_consistent=false;
  if(fault==7)in.secondary_physical.success_contiguous=false;
  if(fault==8)in.secondary_physical.phase=0;
  if(fault==9)in.secondary_render_cost=-1;
  if(fault==10)clock_ns=INT64_MAX-in.secondary_render_cost+1;
  if(fault==11)frame.display_synced=true;
  struct secondary_ass_present_plan early={0};
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  int64_t expected_target=fault==0?secondary_ass_physical_submit_time(
   &in.secondary_physical,native.wall):F;
  if(r.plan.fresh_clock_only || r.plan.valid || r.target!=expected_target)
   fprintf(stderr,"V29 authority fault=%u clock_only=%d valid=%d target=%lld F=%lld\n",
    fault,r.plan.fresh_clock_only,r.plan.valid,(long long)r.target,(long long)F);
  CHECK(!r.plan.fresh_clock_only && !r.plan.valid && r.target==expected_target);
  v29_rejected_scopes++;
 }
 // A FIFO label must not revive a malformed/occupied proposal (deadline=0).
 for(unsigned bad=0;bad<2;bad++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  struct secondary_ass_physical_point shift=secondary_ass_physical_point_at(&in.secondary_physical,native.slot-3);
  in.secondary_physical.phase=shift.wall;in.secondary_physical.phase_slot=shift.slot;
  in.secondary_physical.success_last_id=9;
  if(bad==0)native.wall++;
  else in.secondary_physical.last_base_slot=native.slot;
  int64_t F=native.wall;clock_ns=F-in.secondary_render_cost;frame.pts=F;
  struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,fixture_divisor,fixture_rate);
  CHECK(!old.valid && old.deadline==0 && old.fifo_known && old.fifo_lower>old.target.slot);
  struct secondary_ass_present_plan early={0};
  v29_clear_observation();
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  v29_original_miss(&old,"fixed_fifo_after_target");
  CHECK(!r.plan.valid && !r.plan.fresh_clock_only && r.target==F);
  v29_rejected_scopes++;
 }
 fixture_live_sampler=false;
}
static void v29_clock_edges(void) {
 for(unsigned mode=0;mode<3;mode++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=native.wall+in.secondary_physical.interval/2;
  clock_ns=native.wall-in.secondary_render_cost-100000;frame.pts=F;
  struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,fixture_divisor,fixture_rate);
  struct secondary_ass_physical saved=in.secondary_physical;
  struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
  struct secondary_ass_present_plan early={0};
  v29_clear_observation();v29_clock_advances=true;v29_advance_after=2;
  v29_clock_after=mode==0?old.deadline+3*in.secondary_physical.interval:mode==1?INT64_MAX:0;
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  CHECK(v29_clock_reads>=4);v29_clock_advances=false;
  v29_original_miss(&old,"before_video_due");
  CHECK(!memcmp(&saved,&in.secondary_physical,sizeof(saved)));
  CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
  if(mode==0) {
   CHECK(r.plan.valid && r.plan.fresh_clock_only && r.target==F);
   CHECK(r.plan.target.wall>v29_clock_after+in.secondary_render_cost);
   CHECK(r.plan.target.slot>old.target.slot);
   CHECK(r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
   v29_positive_plans++;
  } else CHECK(!r.plan.valid && !r.plan.fresh_clock_only && r.target==F);
  v29_time_edges++;
 }
 fixture_live_sampler=false;
}
static void v29_long_models(void) {
 if(failures)return;
 const int hz_values[]={60,120,144,165,240,360};
 const int fps_values[]={24,25,30,50,60};
 for(unsigned h=0;h<6;h++)for(unsigned f=0;f<5;f++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v28_setup(&vo,&in,&frame,&driver,&opts,hz_values[h],fps_values[f]);
  in.secondary_render_cost=1000000;in.secondary_redraw_cost=1000000;
  in.secondary_redraw_block_cost=1000000;
  struct secondary_ass_physical physical=in.secondary_physical;
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
   v29_clear_observation();
   struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
   struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,
    fixture_divisor,fixture_rate);
   CHECK(secondary_ass_budget_affordable(in.secondary_render_cost,in.secondary_redraw_cost,
    frame.duration,fixture_divisor*in.secondary_physical.interval));
   struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
   CHECK(r.plan.valid && r.physical && r.plan.display_forecast);
   CHECK(r.plan.base.slot>previous_slot && (r.plan.base.slot-origin)%fixture_divisor==0);
   CHECK(r.plan.target.slot-r.plan.base.slot==fixed.offset && r.plan.deadline==r.plan.target.wall);
   CHECK(!memcmp(&physical,&in.secondary_physical,sizeof(physical)));
   CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
   if(r.plan.fresh_clock_only) {
    CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
    CHECK(r.plan.target.wall>MPMAX(F,clock_ns+in.secondary_render_cost));
    v29_original_miss(&old,old.base.wall<F?"before_video_due":"fixed_display_deadline_expired");
    v29_waits(&vo,&frame,&driver,&r,F);
   } else {
    CHECK(!v29_record_count && r.target==old.submit && !memcmp(&r.plan,&old,sizeof(old)));
   }
   CHECK(actual_sampler_selection(&in,&r.plan));
   CHECK(fixture_sampler.pts>previous_pts && fixture_sampler.origin_slot==origin);
   previous_pts=fixture_sampler.pts;previous_slot=r.plan.base.slot;v29_model_draws++;
   if(failures)return;
  }
  v29_matrix_cases++;
 }
 fixture_live_sampler=false;
}
static void v29_tests(void) {
 unsigned start=checks,before_failures=failures;
 for(unsigned mode=0;mode<4;mode++)for(unsigned scope=0;scope<4;scope++)v29_candidate(mode,scope);
 v29_candidate(4,0);v29_candidate(5,0);
 v29_feature_and_authority();v29_clock_edges();v29_long_models();
 v29_checks=checks-start;
 fprintf(stderr,"V29 fresh retry checks=%u plans=%u rejected=%u time_edges=%u matrix=%u draws=%u failures=%u\n",
  v29_checks,v29_positive_plans,v29_rejected_scopes,v29_time_edges,v29_matrix_cases,v29_model_draws,failures-before_failures);
}
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--parity', required=True, type=Path)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    source, baseline, parity = (p.resolve() for p in (args.source,args.baseline,args.parity))
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    compiler=shutil.which(args.cc);require(compiler,'Compiler absent')
    predecessor=parity/'verify-native-ass-fresh-clock-caller.py'
    require(sha(predecessor.read_bytes())==V28_SHA,'Frozen V28 builder changed')
    base=load('v29_frozen_v28',predecessor)
    caller_path=parity/'verify-native-ass-queue-stage-caller-v26.py'
    gate_path=parity/'verify-native-ass-integration-v26.py'
    require(sha(caller_path.read_bytes())==base.CALLER_SHA,'Frozen caller changed')
    require(sha(gate_path.read_bytes())==base.GATE_SHA,'Frozen declarations changed')
    old_bytes=(baseline/'video/out/vo.c').read_bytes()
    require(sha(old_bytes)==base.BASELINE_VO_SHA,'V22 baseline changed')
    captured={}

    def read(name):
        if name not in captured:captured[name]=(source/name).read_bytes()
        return captured[name].decode('utf-8')

    caller=base.load('v29_actual_caller',caller_path)
    caller.ROOT,caller.BASELINE,caller.GATE,caller.CC=source,baseline,gate_path,Path(compiler).resolve()
    gate=caller.load_gate()
    report={'status':'ACTUAL_FRESH_RETRY_CPU_PREPARING_NOT_RUNTIME',
            'tool_sha256':sha(Path(__file__).read_bytes()),'predecessor_sha256':V28_SHA,
            'caller_sha256':base.CALLER_SHA,'declaration_gate_sha256':base.GATE_SHA,
            'baseline_vo_sha256':base.BASELINE_VO_SHA,'source_root':str(source),
            'GPU_started':False,'CI_started':False,'Display_acceptance':False,'pacing_acceptance':False,
            'cases':{},'boundary_stubs':['Frozen actual Windows declarations and lock endpoints',
                'Observable OSD setter and separate actual sampler',
                'mp_time_ns endpoint: fixed clock or explicit advance after initial proposal',
                'Actual record sink stores all MISS records in order','Observable platform wait signatures'],
            'not_covered':['Full Atomic OSD producer and full VO loop','Windows ABI and backend lifecycle execution',
                'GPU completion','Present API entry','Actual Display or flicker acceptance'],
            'old_counts':{'checks':103149,'v24_checks':1097,'actual_feedback_frames':312,
                'early_prepare_positive':12,'v28_checks':5109078,'v28_plans':2,
                'v28_matrix':30,'v28_draws':340200,'old_exact_cases':32},
            'retry_scope':'New uncaptured queue0 mandatory fresh proposal only; no early/cache retarget',
            'FIFO_unknown_scope':'Allowed when physical/lifecycle/proposal authority is valid, matching original V28 helper'}
    passed=False
    try:
        generated,report['frozen_builder_evidence']=caller.build(gate,read,old_bytes.decode('utf-8'))
        generated=base.caller_boundaries(gate,read,generated,report)
        vo=read('video/out/vo.c')
        require('bool uncaptured_fixed_fresh' in vo and 'bool fresh_clock_retry' in vo,
                'Actual retry source absent')
        # Endpoint instrumentation has no CHECK calls and does not alter any
        # predecessor counter or source caller body. It observes every MISS.
        generated=base.once(generated,'static struct mp_ass_pacing_record recorded;',
            'static struct mp_ass_pacing_record recorded;\n'
            'static struct mp_ass_pacing_record v29_records[32];\n'
            'static uint32_t v29_record_kind[32];static unsigned v29_record_count;\n'
            'static bool v29_clock_advances;static unsigned v29_clock_reads,v29_advance_after;\n'
            'static int64_t v29_clock_after;', 'record/clock observation declarations')
        generated=base.once(generated,'static int64_t mp_time_ns(void) { return clock_ns; }',
            'static int64_t mp_time_ns(void) {\n'
            ' if(v29_clock_advances && v29_clock_reads++>=v29_advance_after)return v29_clock_after;\n'
            ' return clock_ns; }','clock endpoint observation')
        generated=base.once(generated,'(void)global;(void)kind;recorded=*record;',
            '(void)global;recorded=*record;\n'
            ' if(v29_record_count<32){v29_record_kind[v29_record_count]=kind;\n'
            ' v29_records[v29_record_count++]=*record;}','record sink observation')
        generated=base.once(generated,'int main(void) {',base.TESTS+'\nint main(void) {','unchanged V28 tests')
        old=base.once(generated,' return failures ? 7 : 0;\n}',
            ' v28_tests();\n return failures ? 7 : 0;\n}','unchanged V28 execution')
        new=base.once(old,'int main(void) {',TESTS+'\nint main(void) {','V29 tests')
        new=base.once(new,' v28_tests();\n return failures ? 7 : 0;\n}',
            ' v28_tests();\n v29_tests();\n return failures ? 7 : 0;\n}','V29 execution')
        report['old_tests_sha256']=sha(base.TESTS.encode())
        report['retry_tests_sha256']=sha(TESTS.encode())
        report['translation_sha256']=sha(new.encode())
        (output/'actual-fresh-retry-boundary.c').write_text(new,encoding='utf-8',newline='\n')
        if args.inspect_only:
            report['status']='ACTUAL_FRESH_RETRY_BOUNDARY_EXTRACTED_NOT_COMPILED'
        else:
            selection=gate.functions(old)['actual_fresh_selection_boundary']['text']
            pressure=re.search(r'\bbool\s+fresh_clock_only\s*=[^;]+;',selection).group()
            old_variants={'positive':old}

            def old_fault(name,function,before,after,pressure_only=False):
                actual=gate.functions(old)[function]['text']
                if pressure_only:
                    changed_pressure=base.once(pressure,before,after,name+' original pressure declaration')
                    changed=base.once(actual,pressure,changed_pressure,name+' pressure declaration')
                else:changed=base.once(actual,before,after,name)
                old_variants[name]=base.once(old,actual,changed,name+' actual function')

            old_fault('fresh_eligibility_omitted','actual_fresh_selection_boundary',pressure,'bool fresh_clock_only = false;')
            old_fault('feature_scope_lost','actual_fresh_selection_boundary',
                'secondary_forecast_enabled(vo, frame->display_synced, sample_divisor) &&','true &&',True)
            old_fault('repeat_scope_lost','actual_fresh_selection_boundary','!frame->repeat &&','true &&',True)
            old_fault('captured_early_scope_lost','actual_fresh_selection_boundary','!early_plan.valid &&','true &&',True)
            old_fault('ready_overflow_guard_lost','actual_fresh_selection_boundary',
                'physical_now <= INT64_MAX - in->secondary_render_cost','true')
            old_fault('video_target_retimed_to_D','actual_fresh_selection_boundary',
                'target = present_plan.fresh_clock_only ? original_video_target : submit;',
                'target = present_plan.fresh_clock_only ? present_plan.target.wall : submit;')
            old_fault('late_equality_omitted','actual_fresh_late_miss_boundary',
                'flip_call >= present_plan.deadline','flip_call > present_plan.deadline')
            old_fault('after_flip_actual_draw_bit_lost','secondary_trace_plan_missed',
                '.flags = (uint64_t)actual_draw,','.flags = 0,')
            old_fault('late_captured_D_renamed','secondary_trace_plan_missed',
                '.v = {plan->target.slot, plan->target.wall, plan->base.slot,',
                '.v = {plan->target.slot, mp_time_ns(), plan->base.slot,')
            plan_path='video/out/secondary_ass_present_plan.h';header=read(plan_path)
            helper=base.actual_multiline_plan_helper(gate,header,'secondary_ass_present_plan_fresh_clock')
            header_faults={
                'plan_submit_retained_D':base.once(helper,'plan.submit = video_submit;','plan.submit = plan.target.wall;','submit'),
                'fallback_retained_D':base.once(helper,'plan.fallback_submit = video_submit;','plan.fallback_submit = plan.target.wall;','fallback'),
                'lifecycle_wait_retained_D':base.once(helper,'plan.lifecycle_safe_wait = video_submit;','plan.lifecycle_safe_wait = plan.target.wall;','lifecycle'),
                'divided_lattice_lost':base.once(helper,'divisor, after, offset','1, after, offset','lattice'),
                'physical_phase_mutated':base.once(helper,'plan.submit = video_submit;',
                    '((struct secondary_ass_physical *)p)->phase++;\n    plan.submit = video_submit;','phase'),
                'historical_H_mutated':base.once(helper,'plan.submit = video_submit;',
                    '((struct secondary_ass_physical *)p)->delay++;\n    plan.submit = video_submit;','H')}
            retry_variants={'positive':new}
            function=gate.functions(new)['actual_fresh_selection_boundary']['text']
            declaration=re.search(r'\bbool\s+uncaptured_fixed_fresh\s*=[^;]+;',function).group()
            retry_start=function.index('                if (fresh_clock_retry) {')
            retry_end=function.index('\n            }\n            struct secondary_ass_physical_point candidate',retry_start)
            retry=function[retry_start:retry_end]

            def retry_fault(name,before,after,scope='retry'):
                fragment=declaration if scope=='declaration' else retry if scope=='retry' else function
                changed_fragment=base.once(fragment,before,after,name)
                changed=base.once(function,fragment,changed_fragment,name+' actual fragment') if fragment!=function else changed_fragment
                retry_variants[name]=base.once(new,function,changed,name+' actual selection')

            retry_fault('retry_omitted','if (fresh_clock_retry)','if (fresh_clock_retry && false)')
            retry_fault('retry_repeat_scope_lost','!frame->repeat &&','true &&','declaration')
            retry_fault('retry_captured_early_scope_lost','!early_plan.valid &&','true &&','declaration')
            retry_fault('retry_queue_stage_scope_lost','!in->secondary_queue_stage &&','true &&','declaration')
            retry_fault('retry_fixed_scope_lost','in->secondary_fixed_forecast &&','true &&','declaration')
            authority='present_plan.submit > 0 && present_plan.fallback_submit > 0 &&\n                    present_plan.deadline > 0 &&\n                    present_plan.deadline == present_plan.target.wall'
            retry_fault('retry_proposal_authority_lost',authority,'true','declaration')
            retry_fault('retry_original_MISS_omitted',
                'secondary_trace_plan_missed(vo, "before_video_due", "before-draw",\n                                                &present_plan);',
                'if (!uncaptured_fixed_fresh)\n                    secondary_trace_plan_missed(vo, "before_video_due", "before-draw",\n                                                &present_plan);','function')
            retry_fault('retry_old_D_renamed','bool fresh_clock_retry = false;',
                'bool fresh_clock_retry = false;\n                if (uncaptured_fixed_fresh) present_plan.target.wall++;','function')
            retry_fault('retry_old_G_renamed','bool fresh_clock_retry = false;',
                'bool fresh_clock_retry = false;\n                if (uncaptured_fixed_fresh) present_plan.base.wall++;','function')
            retry_fault('retry_zero_clock_guard_lost','retry_now > 0 &&','true &&')
            retry_fault('retry_overflow_guard_lost','retry_now <= INT64_MAX - in->secondary_render_cost','true')
            retry_fault('retry_ready_not_refreshed','retry_now + in->secondary_render_cost','physical_now + in->secondary_render_cost')
            retry_call='present_plan = secondary_forecast_fresh_clock_plan(vo,\n                            retry_ready, original_video_target, native_point,\n                            sample_divisor, native_rate);'
            for name,statement in (
                ('retry_submit_retained_D','present_plan.submit = present_plan.target.wall;'),
                ('retry_fallback_retained_D','present_plan.fallback_submit = present_plan.target.wall;'),
                ('retry_lifecycle_retained_D','present_plan.lifecycle_safe_wait = present_plan.target.wall;'),
                ('retry_deadline_renamed','present_plan.deadline = retry_ready;'),
                ('retry_physical_phase_mutated','in->secondary_physical.phase++;'),
                ('retry_historical_H_mutated','in->secondary_physical.delay++;'),
                ('retry_fixed_offset_mutated','in->secondary_fixed_offset.offset++;')):
                retry_fault(name,retry_call,retry_call+'\n                        '+statement)
            retry_fault('retry_old_task_revived',retry_call,
                '(void)retry_ready;\n                        present_plan.valid = true;\n                        present_plan.fresh_clock_only = true;\n'
                '                        present_plan.submit = original_video_target;\n'
                '                        present_plan.fallback_submit = original_video_target;\n'
                '                        present_plan.lifecycle_safe_wait = original_video_target;')
            retry_fault('retry_lattice_divisor_lost','sample_divisor, native_rate);','1, native_rate);')
            def execute(suite,name,code,mode,flags,negative,include=source):
                cpath=output/(suite+'-'+name+'.c')
                if not cpath.exists():cpath.write_text(code,encoding='utf-8',newline='\n')
                else:require(cpath.read_bytes()==code.encode(),'Existing C changed')
                caller.ROOT=include
                execution=caller.execute_c(cpath,flags)
                caller.ROOT=source
                legacy=json.loads(execution['stdout']) if execution['stdout'].strip() else {}
                matched=re.search(r'V28 fresh clock checks=(\d+) plans=(\d+) matrix=(\d+) draws=(\d+) failures=(\d+)',execution['stderr'])
                v28=dict(zip(('checks','plans','matrix','draws','failures'),map(int,matched.groups()))) if matched else {}
                retry_match=re.search(r'V29 fresh retry checks=(\d+) plans=(\d+) rejected=(\d+) time_edges=(\d+) matrix=(\d+) draws=(\d+) failures=(\d+)',execution['stderr'])
                v29=dict(zip(('checks','plans','rejected','time_edges','matrix','draws','failures'),map(int,retry_match.groups()))) if retry_match else {}
                compiled=(execution.get('compiled') is True and execution.get('compile_returncode')==0 or
                          execution.get('compile_and_run') is True and bool(legacy) and bool(v28) and (suite=='v28' or bool(v29)))
                old_ok=(legacy.get('checks')==103149 and legacy.get('v24_checks')==1097 and legacy.get('failures')==0 and
                        legacy.get('actual_feedback_frames')==312 and legacy.get('early_prepare_positive')==12)
                v28_ok=v28=={'checks':5109078,'plans':2,'matrix':30,'draws':340200,'failures':0}
                if suite=='v28':
                    accepted=compiled and old_ok and (execution['exit_code']==7 and v28.get('failures')==EXPECTED_OLD_FAULT_FAILURES[name] if negative else execution['exit_code']==0 and v28_ok)
                elif negative:
                    accepted=compiled and old_ok and v28_ok and execution['exit_code']==7 and v29.get('failures')==EXPECTED_RETRY_FAULT_FAILURES[name]
                else:
                    accepted=compiled and old_ok and v28_ok and execution['exit_code']==0 and v29==EXPECTED_RETRY
                execution.update({'result':legacy,'v28_result':v28,'v29_result':v29,'negative':negative,
                    'compiled_and_expected':accepted,'translation_sha256':sha(code.encode()),'suite':suite})
                report['cases'][suite+'_'+name+'_'+mode]=execution
                require(accepted,'Actual case rejected: '+suite+'_'+name+'_'+mode+' '+execution['stderr'][-2400:])
                print(json.dumps({'case':suite+'_'+name+'_'+mode,'compiled_and_expected':accepted}),flush=True)

            for name,code in old_variants.items():
                for mode,flags in (('normal',[]),('NDEBUG',['-DNDEBUG'])):execute('v28',name,code,mode,flags,name!='positive')
            for name,changed in header_faults.items():
                include=output/('headers-v28-'+name);include.mkdir()
                for relative,data in captured.items():
                    if relative.endswith('.h'):
                        path=include/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                (include/plan_path).write_text(base.once(header,helper,changed,name+' header'),encoding='utf-8',newline='\n')
                for mode,flags in (('normal',[]),('NDEBUG',['-DNDEBUG'])):execute('v28',name,old,mode,flags,True,include)
            require(len(report['cases'])==32,'All frozen V28 cases required')
            for name,code in retry_variants.items():
                for mode,flags in (('normal',[]),('NDEBUG',['-DNDEBUG'])):execute('v29',name,code,mode,flags,name!='positive')
            report['expected_retry_result']=EXPECTED_RETRY
            report['expected_retry_fault_failures']=EXPECTED_RETRY_FAULT_FAILURES
            report['expected_old_fault_failures']=EXPECTED_OLD_FAULT_FAILURES
            report['retry_faults']=len(retry_variants)-1
            report['exact_cases']=32+2*len(retry_variants)
            require(len(report['cases'])==report['exact_cases'],'Every new fault in both modes required')
            require(not any((source/name).read_bytes()!=data for name,data in captured.items()),'Source changed during execution')
            report['status']='ACTUAL_FRESH_RETRY_CALLER_CPU_PASS_NOT_RUNTIME';passed=True
    except (ValueError,KeyError,OSError,subprocess.TimeoutExpired) as error:
        report['status']='ACTUAL_FRESH_RETRY_CPU_GATE_NOT_READY_OR_FAIL';report['error']=str(error)
    report['source_sha256']={name:sha(data) for name,data in captured.items()}
    report['inputs_changed_during_extraction']=[name for name,data in captured.items() if (source/name).read_bytes()!=data]
    target=output/'fresh-retry-caller.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(target),'report_sha256':sha(target.read_bytes())}))
    return 0 if passed or args.inspect_only and report['status']=='ACTUAL_FRESH_RETRY_BOUNDARY_EXTRACTED_NOT_COMPILED' else 1


if __name__=='__main__':
    raise SystemExit(main())
