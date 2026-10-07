"""Execute the real VO redraw budget tail with the existing real VO closure.

The platform/OSD endpoints remain the explicitly declared boundaries of the
frozen V24 caller harness. This does not execute the complete VO thread or GPU.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CALLER_SHA = 'adfa8a5f940123c4c47ddb276db5fbb570b9eab32b72a3c6b67c7ffd4a8eba8e'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(value, message):
    if not value:
        raise ValueError(message)


TESTS = r'''
static void ui_probe_recovery_cases(void) {
 const int rates[]={60,120,144,165,240,360};
 for(unsigned r=0;r<6;r++)for(int mode=0;mode<2;mode++)
 for(int ds=0;ds<2;ds++)for(int full=0;full<2;full++)
 for(int active=0;active<2;active++) {
  struct vo vo;struct vo_internal in;struct vo_frame retained;
  struct vo_driver driver;struct mp_vo_opts opts;
  setup(&vo,&in,&retained,&driver,&opts);
  const int64_t T=1000000000LL/rates[r],start=20000000000LL;
  in.secondary_fixed_forecast=mode;retained.display_synced=ds;
  int64_t deadline=start+1000000000;
  in.secondary_next_probe=deadline;
  // Explicit UI events arrive before expiry. Only accepted pose reuse may
  // retain the deadline; legacy/display-sync/rate-zero/full-redraw stay exact.
  for(int k=1;k<=26;k++) {
   clock_ns=start+k*250000000LL;
   bool reuse=mode && !ds;
   int64_t previous=in.secondary_next_probe;
   in.secondary_last_draw=clock_ns-4*T/5;
   unsigned old_count=in.secondary_redraw_budget.count;
   actual_redraw_budget_boundary(&vo,reuse,full,active?1e9/T:0,4*T/5);
   CHECK(in.secondary_next_probe==(!full && active && !reuse
     ? clock_ns+1000000000 : previous));
   CHECK(in.secondary_redraw_budget.count==(!full && active
     ? (old_count<3?old_count+1:3):old_count));
   CHECK(!in.lock && !lock_depth);
   if(!full && active) {
    CHECK(in.secondary_redraw_cpu_cost==4*T/5);
    CHECK(in.secondary_redraw_cost==4*T/5);
    CHECK(!secondary_ass_budget_affordable(T/4,4*T/5,20*T,T));
   }
  }
  if(mode && !ds && !full && active) {
   CHECK(in.secondary_next_probe==deadline);
   CHECK(secondary_ass_budget_probe_due(T/4,20*T,T,clock_ns,deadline));
   CHECK(!secondary_ass_budget_probe_due(16*T,20*T,T,clock_ns,deadline));
  }
  // An actual grid draw re-arms the existing one-second bound even when
  // expensive. Removing all re-arm would produce repeated unbounded probes.
  clock_ns=start+7000000000LL;in.secondary_last_draw=clock_ns-4*T/5;
  actual_redraw_budget_boundary(&vo,false,false,1e9/T,4*T/5);
  CHECK(in.secondary_next_probe==clock_ns+1000000000);
  CHECK(!secondary_ass_budget_probe_due(T/4,20*T,T,clock_ns+999999999,
    in.secondary_next_probe));
  CHECK(secondary_ass_budget_probe_due(T/4,20*T,T,clock_ns+1000000000,
    in.secondary_next_probe));
 }
 // Exercise the actual outer scheduler after UI reuses a pose at expiry.
 // Incoming frame/OSD getter values are explicit fixture inputs, not timing
 // observations. Real affordability, headroom, plan and probe guards execute.
 for(unsigned r=0;r<6;r++)for(int N=1;N<=4;N++) {
  struct vo vo;struct vo_internal in;struct vo_frame retained;
  struct vo_driver driver;struct mp_vo_opts opts;
  setup(&vo,&in,&retained,&driver,&opts);
  const int64_t T=1000000000LL/rates[r],O=1000000000;
  in.secondary_queue_stage=false;in.secondary_display_forecast=true;
  in.secondary_fixed_forecast=true;in.vsync_interval=T;in.reported_display_fps=1e9/T;
  retained.duration=20*N*T;retained.pts=O;
  in.secondary_physical=(struct secondary_ass_physical){.phase=O,.phase_slot=100,
   .interval=T,.epoch=7,.sync_qpc_ns=O,.sync_count=100,.sync_slot=100,
   .sync_segment_consistent=true,.measure_qpc_ns=O,.measure_count=100,
   .periods={T,T,T},.period_count=3,.period_next=3,.delay=1,
   .delay_samples={1,1,1},.delay_count=3,.success_generation=3,.success_contiguous=true};
  fixture_clock=(struct secondary_ass_clock){.valid=true,.pts=10,.speed=1,.wall=O};
  fixture_rate=1e9/(N*(double)T);fixture_divisor=N;fixture_live_sampler=true;
  struct secondary_ass_present_plan seed=secondary_forecast_plan(&vo,
   secondary_ass_physical_point_at(&in.secondary_physical,110),N,fixture_rate);
  CHECK(seed.valid);CHECK(actual_sampler_selection(&in,&seed));
  clock_ns=seed.target.wall+10000;retained.pts=seed.base.wall;
  struct vo_vsync_info vsync=host_vsync(&in,&seed,1,&seed,1,clock_ns);
  secondary_physical_feedback(&vo,&vsync,seed.target,&seed);
  in.secondary_render_cost=N*T/4;
  in.secondary_redraw_budget=(struct secondary_ass_budget){{N*T*4/5,N*T*4/5,N*T*4/5},3,0};
  in.secondary_redraw_block_budget=in.secondary_redraw_budget;
  in.secondary_next_probe=clock_ns;
  in.secondary_last_draw=clock_ns-N*T*4/5;
  actual_redraw_budget_boundary(&vo,true,false,fixture_rate,N*T*4/5);
  bool manual=false;
  int64_t wake=outer_timer_boundary(&vo,false,false,&manual);
  if(!manual) {
   CHECK(wake>clock_ns && wake<retained.pts+retained.duration);
   clock_ns=wake;(void)outer_timer_boundary(&vo,false,false,&manual);
  }
  CHECK(manual && actual_outer_task.recovery_probe && actual_outer_task.plan.valid);
  in.paused=true;
  (void)outer_timer_boundary(&vo,false,false,&manual);
  CHECK(!manual && !actual_outer_task.recovery_probe);
  in.paused=false;
  (void)outer_timer_boundary(&vo,false,false,&manual);
  CHECK(manual && actual_outer_task.recovery_probe);
 }
 fixture_live_sampler=false;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    captured = {}
    def read(name):
        data = (args.source/name).read_bytes()
        captured[name] = data
        return data.decode('utf-8')
    caller_path = HERE/'verify-native-ass-queue-stage-caller.py'
    require(hashlib.sha256(caller_path.read_bytes()).hexdigest() == CALLER_SHA,
            'Frozen V24 caller tool changed')
    caller = load('v25_ui_frozen_vo_caller', caller_path)
    caller.ROOT = args.source.resolve()
    caller.BASELINE = args.baseline.resolve()
    caller.GATE = HERE/'verify-native-ass-integration.py'
    caller.CC = Path(shutil.which(args.cc) or args.cc).resolve()
    gate = caller.load_gate()
    original = (args.baseline/'video/out/vo.c').read_text(encoding='utf-8')
    require(caller.sha(original.encode()) == 'e4e7bd710c84c43af548a66e8950cfb69814db478a4a889239572d3292bafefd',
            'Frozen V22 baseline changed')
    generated, evidence = caller.build(gate, read, original)
    redraw = gate.functions(read('video/out/vo.c'))['do_redraw']['text']
    marker = 'if (!full_redraw && secondary_rate > 0) {'
    begin = redraw.index(marker)
    end = gate.balanced(gate.mask_c(redraw), redraw.index('{', begin))
    fragment = redraw[begin:end]
    wrapper = '''static void actual_redraw_budget_boundary(struct vo *vo,
 bool fixed_pose_reuse,bool full_redraw,double secondary_rate,int64_t cpu_cost) {
 struct vo_internal *in=vo->in;
 (void)fixed_pose_reuse;
''' + fragment + '\n}\n'
    main_marker = 'int main(void) {'
    require(generated.count(main_marker) == 1, 'Actual fixture main ambiguous')
    generated = generated.replace(main_marker, wrapper + TESTS + main_marker, 1)
    # Preserve the frozen original test counts by executing the new cases after
    # the old positive suite has reported them. New failures still return7.
    tail = ' return failures ? 7 : 0;\n}'
    require(generated.count(tail) == 1, 'Actual fixture final return ambiguous')
    generated = generated.replace(tail, ''' unsigned v25_before=checks;
 ui_probe_recovery_cases();
 fprintf(stderr,"V25_UI_CHECKS=%u FAILURES=%u\\n",checks-v25_before,failures);
 return failures ? 7 : 0;
}''', 1)
    report = {'scope':'REAL_VO_STRUCTS_BUDGET_TAIL_AND_OUTER_SCHEDULER_CPU',
        'GPU_started':False,'pacing_acceptance':False,'evidence':evidence,
        'budget_fragment_sha256':caller.sha(fragment.encode()),'cases':{}}
    variants = {'positive':generated,
        'UI_defers_probe_mutant':generated.replace('if (!fixed_pose_reuse)\n', 'if (true)\n', 1),
        'grid_never_rearms_mutant':generated.replace('in->secondary_next_probe = mp_time_ns() + MP_TIME_S_TO_NS(1);',
                                                    '(void)in->secondary_next_probe;', 1)}
    require(variants['positive'] != variants['UI_defers_probe_mutant'] != variants['grid_never_rearms_mutant'],
            'Actual budget faults not injected')
    for name, source in variants.items():
        path = args.output/(name+'.c')
        path.write_text(source, encoding='utf-8', newline='\n')
        for mode,flags in [('normal',[]),('NDEBUG',['-DNDEBUG'])]:
            result = caller.execute_c(path, flags)
            report['cases'][name+'_'+mode] = result
    unchanged = all((args.source/name).read_bytes() == data for name,data in captured.items())
    report['source_sha256'] = {name:caller.sha(data) for name,data in captured.items()}
    report['source_unchanged'] = unchanged
    passed = unchanged
    for name,result in report['cases'].items():
        if name.startswith('positive_'):
            passed &= result['exit_code'] == 0 and 'FAILURES=0' in result['stderr']
        else:
            passed &= result['exit_code'] == 7 and 'check failed' in result['stderr']
    report['status'] = 'PASS_CPU_NOT_GPU' if passed else 'FAIL_CPU'
    (args.output/'ui-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'cases':len(report['cases']),
                     'results':{name:(r['exit_code'],r['stderr'][-120:]) for name,r in report['cases'].items()}}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
