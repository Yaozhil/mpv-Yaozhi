"""Compile reviewed recovery contracts against exact final VO/OSD functions."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]
OSD_FUNCTIONS = (
    'osd_get_secondary_physical_next_sample_slot',
    'osd_get_secondary_physical_next_sample_time',
    'osd_get_secondary_physical_sample_divisor',
    'osd_get_secondary_sample_snapshot',
    'osd_set_secondary_physical_forecast_time',
    'osd_hold_secondary_sample',
)
VO_FUNCTIONS = (
    'secondary_plan_enabled', 'secondary_fixed_forecast_offset',
    'secondary_forecast_next', 'secondary_forecast_fresh_clock_plan',
    'secondary_forecast_fresh_video_plan', 'secondary_planning_state',
    'secondary_next_sample',
)
SOURCE_INPUTS = (
    'video/out/vo.c', 'sub/osd.c', 'sub/secondary_ass_clock.h',
    'video/out/secondary_ass_fresh_video.h',
    'video/out/secondary_ass_present_plan.h',
    'video/out/secondary_ass_physical.h',
    'video/out/secondary_ass_budget.h',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function(source, name):
    # Keep exactly the production declaration and body, without reconstructing
    # a scheduler or replacing any production timing operation in the fixture.
    at = source.index(name+'(')
    start = source.rfind('\n\n', 0, at)+2
    brace = source.index('{', at)
    depth, end = 1, brace+1
    while depth:
        depth += (source[end] == '{')-(source[end] == '}')
        end += 1
    return source[start:end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--cc', default='cc')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source = a.source.resolve()
    spec = importlib.util.spec_from_file_location('native_freeze_gate', HERE/'verify-native-freeze-source.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    result = dict(status='NATIVE_FREEZE_ACTUAL_CALLER_CPU_FAILED',
        runtime_verified=False, Display_accepted=False, contracts=[])
    try:
        lock = json.loads((HERE/'native-freeze-lock.json').read_bytes())
        gate.validate_lock(lock)
        source_hashes = {rel: sha(source/rel) for rel in SOURCE_INPUTS}
        result['source_sha256'] = source_hashes
        result['native_freeze_lock_sha256'] = sha(HERE/'native-freeze-lock.json')
        for contract in lock['cpu_contracts']:
            fixture = gate.checked_file(CONFIG, contract['runner'], lock['tools_sha256'][contract['runner']])
            with tempfile.TemporaryDirectory(prefix='native-freeze-cpu-', ignore_cleanup_errors=True) as folder:
                folder = Path(folder)
                executable = folder/('contract.exe' if os.name == 'nt' else 'contract')
                compile_args = [a.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I'+str(source), '-I'+str(source/'video/out'), '-I'+str(folder)]
                entry = dict(id=contract['id'], contract_sha256=sha(fixture))
                if contract['kind'] == 'extracted-epoch':
                    osd = (source/'sub/osd.c').read_text(encoding='utf-8')
                    vo = (source/'video/out/vo.c').read_text(encoding='utf-8')
                    fragments = {name: function(osd, name) for name in OSD_FUNCTIONS}
                    fragments.update({name: function(vo, name) for name in VO_FUNCTIONS})
                    header = folder/'extracted-final.h'
                    header.write_text('/* Exact bound production functions. */\n'+
                        '\n\n'.join(fragments.values())+'\n', encoding='utf-8', newline='\n')
                    compile_args.append('-DVARIANT_HEADER="extracted-final.h"')
                    entry['extracted_sha256'] = sha(header)
                    entry['production_function_sha256'] = {
                        name: hashlib.sha256(body.encode()).hexdigest() for name, body in fragments.items()}
                compile_args += [str(fixture), '-o', str(executable)]
                built = subprocess.run(compile_args, capture_output=True, text=True, timeout=60)
                entry.update(compile_exit=built.returncode, compile_stdout=built.stdout,
                    compile_stderr=built.stderr)
                result['contracts'].append(entry)
                gate.require(built.returncode == 0, 'Actual-source recovery contract compile failed')
                ran = subprocess.run([str(executable), *contract.get('run_arguments', [])],
                    capture_output=True, text=True, timeout=60)
                entry.update(run_exit=ran.returncode, run_stdout=ran.stdout, run_stderr=ran.stderr,
                    executable_sha256=sha(executable))
                gate.require(ran.returncode == 0 and
                    ran.stdout.startswith(contract['expected_stdout_prefix']),
                    'Actual-source recovery contract failed or omitted success marker')
        gate.require(source_hashes == {rel: sha(source/rel) for rel in SOURCE_INPUTS},
            'CPU contracts modified bound production source')
        result['status'] = 'NATIVE_FREEZE_ACTUAL_CALLER_CPU_PASS_NOT_RUNTIME'
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
