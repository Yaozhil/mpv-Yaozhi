#!/usr/bin/env python3
"""Actual fixed-forecast budget recovery caller gate, CPU only.

Builds real declarations/caller fragments using the SHA-locked V26 builder.
Old assertions and their output counters remain unchanged. New checks and
runtime-rejected faults do not imply complete VO, ABI, GPU or Display results.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CALLER_SHA = '197d664c74af4cfff594e34c23c19d648de24cb94f18fd6da10afac80434d558'
GATE_SHA = 'ab1f7605d6cd992f4a5d0ef1e48a436331ec4e61642557378fb912b93fe71154'
BASELINE_VO_SHA = 'e4e7bd710c84c43af548a66e8950cfb69814db478a4a889239572d3292bafefd'
NEW_CHECKS = 3801
EXPECTED_GRIDS = 57
TESTS = '\nstatic unsigned v27_new_checks,v27_grid_count;\nstatic void v27_actual_probe_case(bool fixed,int64_t next_probe,int64_t fresh,int64_t redraw,int64_t lead) {\n const int64_t T=6944481,N=2,O=1000000000,interval=N*T;\n unsigned grids=0;\n for(int phase=0;phase<64;phase++) {\n  struct vo vo;struct vo_internal in;struct vo_frame retained;\n  struct vo_driver driver;struct mp_vo_opts opts;setup(&vo,&in,&retained,&driver,&opts);\n  fixture_divisor=N;fixture_rate=1e9/(double)interval;\n  in.secondary_queue_stage=false;in.secondary_display_forecast=true;\n  in.secondary_fixed_forecast=fixed;in.vsync_interval=T;in.reported_display_fps=1e9/T;\n  retained.duration=20000000;\n  in.secondary_physical=(struct secondary_ass_physical){.phase=O,.phase_slot=100,\n   .interval=T,.epoch=7,.sync_qpc_ns=O,.sync_count=100,.sync_slot=100,\n   .sync_segment_consistent=true,.measure_qpc_ns=O,.measure_count=100,\n   .periods={T,T,T},.period_count=3,.period_next=3,.delay=1,\n   .delay_samples={1,1,1},.delay_count=3,.success_generation=3,.success_contiguous=true};\n  fixture_clock=(struct secondary_ass_clock){.valid=true,.pts=10,.speed=1,.wall=O};\n  fixture_live_sampler=true;\n  struct secondary_ass_present_plan seed=secondary_forecast_plan(&vo,\n   secondary_ass_physical_point_at(&in.secondary_physical,110),N,fixture_rate);\n  CHECK(seed.valid && actual_sampler_selection(&in,&seed));\n  clock_ns=seed.target.wall+10000;\n  struct vo_vsync_info vsync=host_vsync(&in,&seed,1,&seed,1,clock_ns);\n  secondary_physical_feedback(&vo,&vsync,seed.target,&seed);\n  struct secondary_ass_physical saved=in.secondary_physical;\n  clock_ns=seed.target.wall+interval*10+phase*interval/64+fresh;\n  retained.pts=clock_ns-fresh+lead;\n  in.secondary_render_cost=fresh;in.secondary_redraw_cost=redraw;\n  in.secondary_redraw_block_cost=redraw+405700;in.secondary_redraw_gpu_cost=100000;\n  in.secondary_next_probe=next_probe;\n  CHECK(!secondary_ass_budget_affordable(fresh,redraw,retained.duration,interval));\n  bool manual=false;int64_t wake=outer_timer_boundary(&vo,false,false,&manual);\n  if(!manual && wake>clock_ns && wake<retained.pts+retained.duration) {\n   clock_ns=wake;(void)outer_timer_boundary(&vo,false,false,&manual);\n  }\n  if(manual && actual_outer_task.point.slot>0) {\n   grids++;CHECK(fixed && next_probe==0 && fresh<retained.duration*.75);\n   CHECK(actual_outer_task.recovery_probe);\n   CHECK(actual_outer_task.plan_enabled && actual_outer_task.plan.valid);\n   CHECK(actual_outer_task.plan.target.slot-actual_outer_task.plan.base.slot==1);\n   CHECK(actual_outer_task.plan.base.slot>seed.base.slot);\n   CHECK((actual_outer_task.plan.base.slot-seed.base.slot)%N==0);\n   CHECK(in.secondary_physical.phase==saved.phase && in.secondary_physical.phase_slot==saved.phase_slot);\n   CHECK(in.secondary_physical.delay==saved.delay);\n   int64_t original=retained.pts;\n   // Independently enforce the unchanged actual submission boundary/margin.\n   int64_t cost=MPMAX(in.secondary_redraw_gpu_cost,MPMIN(in.secondary_redraw_block_cost,interval));\n   CHECK(secondary_ass_budget_headroom(retained.duration,\n      MPMAX(clock_ns,actual_outer_task.plan.submit),get_current_frame_end(&vo)-in.flip_queue_offset,\n      fresh,cost,MP_TIME_S_TO_NS(.002)));\n   bool physical=false,updated=true;struct secondary_ass_physical_point point={0};\n   CHECK(actual_redraw_guard_boundary(&vo,0,0,&actual_outer_task));\n   CHECK(actual_redraw_pose_boundary(&vo,&actual_outer_task,&physical,&updated,&point));\n   CHECK(physical && !updated && point.slot==actual_outer_task.plan.target.slot);\n   CHECK(retained.pts==original);\n   struct secondary_ass_grid_task missing=actual_outer_task;missing.recovery_probe=false;\n   CHECK(!actual_redraw_pose_boundary(&vo,&missing,&physical,&updated,&point));\n  }\n }\n fixture_live_sampler=false;\n if(fixed && next_probe==0 && fresh==3974400 && redraw==11239000 && lead==8000000) {\n  CHECK(grids>0);v27_grid_count=grids;\n } else CHECK(grids==0);\n}\nstatic void v27_actual_probe_tests(void) {\n unsigned start=checks;\n CHECK(!secondary_ass_budget_probe_due(3974400,20000000,13888962,2000000000,0));\n CHECK(secondary_ass_budget_fixed_probe_due(3974400,20000000,13888962,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(-1,20000000,13888962,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(3974400,0,13888962,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(3974400,-1,13888962,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(3974400,20000000,0,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(15000000,20000000,13888962,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(15000001,20000000,13888962,2000000000,0));\n CHECK(!secondary_ass_budget_fixed_probe_due(3974400,20000000,13888962,1999999999,2000000000));\n CHECK(secondary_ass_budget_fixed_probe_due(3974400,20000000,13888962,2000000000,2000000000));\n v27_actual_probe_case(true,0,3974400,11239000,8000000);\n v27_actual_probe_case(false,0,3974400,11239000,8000000);\n v27_actual_probe_case(true,3000000000,3974400,11239000,8000000);\n v27_actual_probe_case(true,0,15000000,11239000,8000000);\n v27_actual_probe_case(true,0,3974400,13888962,0);\n v27_new_checks=checks-start;\n fprintf(stderr,"V27 actual new checks=%u grids=%u failures=%u\\n",v27_new_checks,v27_grid_count,failures);\n}\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_once(text, before, after, purpose):
    require(before != after and text.count(before) == 1,
            'Nonunique or unchanged fault anchor: ' + purpose)
    return text.replace(before, after, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path,
                        help='Existing SHA-locked V22 baseline, shared with the frozen caller gate')
    parser.add_argument('--cc', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    require(source.is_dir() and baseline.is_dir() and source != baseline,
            'Distinct existing source and V22 baseline required')
    compiler = shutil.which(args.cc)
    require(compiler, 'Compiler not found: ' + args.cc)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    caller_path = HERE / 'verify-native-ass-queue-stage-caller-v26.py'
    gate_path = HERE / 'verify-native-ass-integration-v26.py'
    require(sha(caller_path.read_bytes()) == CALLER_SHA, 'Frozen V26 caller builder changed')
    require(sha(gate_path.read_bytes()) == GATE_SHA, 'Frozen actual declaration gate changed')
    baseline_bytes = (baseline / 'video/out/vo.c').read_bytes()
    require(sha(baseline_bytes) == BASELINE_VO_SHA, 'Frozen V22 baseline VO changed')
    captured = {}
    baseline_captured = {'video/out/vo.c': baseline_bytes}

    def read(path):
        if path not in captured:
            captured[path] = (source / path).read_bytes()
        return captured[path].decode('utf-8')

    caller = load('fixed_budget_recovery_v26_real_caller', caller_path)
    caller.ROOT, caller.BASELINE = source, baseline
    caller.GATE, caller.CC = gate_path, Path(compiler).resolve()
    gate = caller.load_gate()
    for path in gate.HEADERS:
        if (baseline / path).is_file():
            baseline_captured[path] = (baseline / path).read_bytes()
    report = {
        'status': 'FIXED_BUDGET_RECOVERY_IN_PROGRESS',
        'GPU_started': False, 'CI_started': False, 'pacing_acceptance': False,
        'scope': 'REAL_DECLARATIONS_ACTUAL_OUTER_REDRAW_BUDGET_HELPER_CPU',
        'tool_sha256': sha(Path(__file__).read_bytes()),
        'caller_builder_sha256': CALLER_SHA, 'declaration_gate_sha256': GATE_SHA,
        'baseline_vo_sha256': BASELINE_VO_SHA,
        'expected_counts': {'old_checks': 103149, 'old_fixed_checks': 1097,
                            'new_checks': NEW_CHECKS, 'new_grids': EXPECTED_GRIDS,
                            'old_feedback_frames': 312, 'old_early_prepare_positive': 12},
        'boundary_stubs': ['Windows endpoints with real declarations/lock wrappers',
                           'Real OSD prototypes, scalar clock/sampler fixture',
                           'Observable OSD pose setter endpoint, not actual ASS image drawing',
                           'Logging, pacing sink and talloc endpoints'],
        'not_covered': ['Complete VO thread, OS scheduler, Windows ABI, GPU/Present/Display',
                        'Actual OSD Atomic body is covered by the separate GCC integration gate',
                        'Previous phase model nine late samples and no-slack refusals remain; not all-phase success'],
        'cases': {},
    }
    passed = False
    try:
        generated, evidence = caller.build(gate, read, baseline_bytes.decode('utf-8'))
        report['evidence'] = evidence
        functions = gate.functions(read('video/out/vo.c'))
        redraw = functions['do_redraw']['text']
        outer = functions['vo_thread']['text']
        actual_redraw = re.search(r'\bbool\s+physical_phase\s*=[^;]+;', redraw)
        actual_outer = re.search(r'\bbool\s+probe\s*=\s*!affordable[^;]+;', outer)
        require(actual_redraw and actual_outer, 'Actual V27 caller expressions absent')
        require('secondary_ass_budget_fixed_probe_due' in actual_redraw.group() and
                'secondary_ass_budget_fixed_probe_due' in actual_outer.group(),
                'Both actual fixed recovery callsites are required')
        report['actual_expressions'] = {
            'redraw': actual_redraw.group(), 'outer': actual_outer.group(),
            'redraw_sha256': sha(actual_redraw.group().encode()),
            'outer_sha256': sha(actual_outer.group().encode()),
        }
        main_marker = 'int main(void) {'
        generated = replace_once(generated, main_marker, TESTS + '\n' + main_marker,
                                 'append new cases without changing old cases')
        tail = ' return failures ? 7 : 0;\n}'
        generated = replace_once(generated, tail,
            ' v27_actual_probe_tests();\n return failures ? 7 : 0;\n}',
            'execute new cases after old unchanged JSON counters')
        report['translation_sha256'] = sha(generated.encode())
        variants = {'positive': generated}

        def fault(name, function, before, after):
            actual = gate.functions(generated)[function]['text']
            changed = replace_once(actual, before, after, name)
            variants[name] = replace_once(generated, actual, changed, name + ' function')

        fault('outer_eligibility_omitted', 'outer_timer_boundary', actual_outer.group(),
              'bool probe = !affordable && secondary_ass_budget_probe_due(secondary_cost,\n'
              '                secondary_duration, interval, now, secondary_probe);')
        fault('redraw_eligibility_omitted', 'actual_redraw_pose_boundary',
              'secondary_ass_budget_fixed_probe_due(', 'secondary_ass_budget_probe_due(')
        fault('fixed_recovery_bit_omitted', 'outer_timer_boundary',
              '.recovery_probe = in->secondary_fixed_forecast && probe,', '.recovery_probe = false,')
        fault('fixed_scope_lost', 'outer_timer_boundary',
              'bool probe = !affordable && (in->secondary_fixed_forecast',
              'bool probe = !affordable && (true')
        actual = gate.functions(generated)['outer_timer_boundary']['text']
        require(actual.count('MP_TIME_S_TO_NS(0.002)') == 2, 'Original headroom margins changed')
        variants['margin_lost'] = replace_once(generated, actual,
            actual.replace('MP_TIME_S_TO_NS(0.002)', 'MP_TIME_S_TO_NS(0.0)'), 'margin_lost function')
        budget_path = 'video/out/secondary_ass_budget.h'
        budget = read(budget_path)
        helper = gate.functions(budget)['secondary_ass_budget_fixed_probe_due']['text']
        report['helper_sha256'] = sha(helper.encode())
        header_faults = {
            'cooldown_lost': replace_once(helper, 'now >= next_probe',
                                         '((void)now, (void)next_probe, true)', 'cooldown_lost helper'),
            'overload_lost': replace_once(helper, 'fresh < duration * 0.75',
                                         'true', 'overload_lost helper'),
        }

        def execute(name, code, mode, flags, negative, include=source):
            path = output / (name + '.c')
            if not path.exists():
                path.write_text(code, encoding='utf-8', newline='\n')
            else:
                require(path.read_bytes() == code.encode(), 'Existing case changed: ' + name)
            caller.ROOT = include
            execution = caller.execute_c(path, flags)
            caller.ROOT = source
            result = json.loads(execution['stdout']) if execution['stdout'].strip() else {}
            matched = re.search(r'V27 actual new checks=(\d+) grids=(\d+) failures=(\d+)', execution['stderr'])
            new_result = ({'checks': int(matched[1]), 'grids': int(matched[2]),
                           'failures': int(matched[3])} if matched else {})
            compiled = (execution.get('compiled') is True or
                        execution.get('compile_and_run') is True and execution['exit_code'] in (0, 7))
            if negative:
                accepted = compiled and execution['exit_code'] == 7 and (
                    result.get('failures', 0) > 0 or new_result.get('failures', 0) > 0)
            else:
                accepted = compiled and execution['exit_code'] == 0 and (
                    result.get('checks') == 103149 and result.get('v24_checks') == 1097 and
                    result.get('failures') == 0 and result.get('actual_feedback_frames') == 312 and
                    result.get('early_prepare_positive') == 12 and
                    new_result == {'checks': NEW_CHECKS, 'grids': EXPECTED_GRIDS, 'failures': 0})
            execution.update({'result': result, 'new_result': new_result, 'negative': negative,
                              'compiled_and_expected': accepted,
                              'translation_sha256': sha(code.encode())})
            report['cases'][name + '_' + mode] = execution
            require(accepted, 'Case did not compile and give expected result: ' + name + '_' + mode +
                    ' ' + execution['stderr'][-1000:])

        for name, code in variants.items():
            for mode, flags in (('normal', []), ('NDEBUG', ['-DNDEBUG'])):
                execute(name, code, mode, flags, name != 'positive')
        for name, changed in header_faults.items():
            include = output / ('headers-' + name)
            include.mkdir()
            for relative, data in captured.items():
                if relative.endswith('.h'):
                    dest = include / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
            (include / budget_path).write_text(replace_once(budget, helper, changed, name + ' header'),
                                              encoding='utf-8', newline='\n')
            for mode, flags in (('normal', []), ('NDEBUG', ['-DNDEBUG'])):
                execute(name, generated, mode, flags, True, include)
        require(len(report['cases']) == 16, 'Require positive two modes and seven faults two modes')
        changed_source = [p for p, data in captured.items() if (source / p).read_bytes() != data]
        changed_baseline = [p for p, data in baseline_captured.items() if (baseline / p).read_bytes() != data]
        report['inputs_changed_during_run'] = changed_source
        report['baseline_changed_during_run'] = changed_baseline
        require(not changed_source and not changed_baseline, 'Source or baseline changed during execution')
        passed = True
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
    report['source_sha256'] = {p: sha(data) for p, data in captured.items()}
    report['baseline_sha256'] = {p: sha(data) for p, data in baseline_captured.items()}
    report['status'] = ('ACTUAL_FIXED_BUDGET_RECOVERY_CPU_PASS_NOT_RUNTIME' if passed else
                        'ACTUAL_FIXED_BUDGET_RECOVERY_CPU_FAIL')
    target = output / 'fixed-budget-recovery.json'
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(target),
                      'report_sha256': sha(target.read_bytes()), 'cases': len(report['cases']),
                      'expected_counts': report['expected_counts']}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
