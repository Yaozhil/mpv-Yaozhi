"""Fast CPU GCC gate for exact V27 replay; no dependencies, SDK, GPU or core build."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

# Import the adjacent gate without leaving a cache in the audited checkout.
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]
BASE_COMMIT = 'c318236b8882af860f16f936225430ad053a2179'
ARCHIVE_SHA = '4d104937a06fbac23e79eb91019b4ee834ea516eb4b8d5574acae15c3fc8933d'
PARITY_SHA = 'e260b59f67babd3c5a94edd98611b6ea7e37426666fcaaef9ca19a8a232cb207'
BASELINE_GATE_SHA = '670b01d525a6ab7790c0643606f262b2ba8da0d79d797ec54a95c9592ef61348'
V22_REFERENCE_GATE_SHA = 'dbaed04501303ea866ca1d3bacc9b69ed173724dbbf1e82fad2d385fcf4d40b9'
V22_SOURCE_COMMIT = 'e88232a260f8a1764f1df7747e162ebcdb63adee'
V22_LINUX_TREE = 'e43fa32e4841ce1562f508293af7fc8371553d3f'
V22_PATCH_SHA = 'a18de8b2528d1014adce5dd95d0cc2293a011203c753eeb6b5a515df4c3b1a04'
V24_SOURCE_COMMIT = 'b92d96326d9e797ccc763b15e7bbbf1d9195f64a'
V24_SOURCE_TREE = '8815cb8d634d1b48b27367367c2b2df38abee23a'
V24_PATCH_SHA = '40dfadefd8ab98c764faea2bf8e8dc54281f63ed9a87f6536773c5a5c0c16ab8'
V25_SOURCE_COMMIT = 'ed8e556282c9c4e37a71dfbbeb85d24e6fdf1a49'
V25_SOURCE_TREE = '23399d1e81d71e78792370ce0699f6b5aaf1fadb'
V25_PATCH_SHA = '4c091a956ca30dad116d126927a9c84a17b34ee8875a90ba7dbc3681bd66089a'
V26_SOURCE_COMMIT = '024a4986affb4a4ef082b8e7b5be73528bdfaa27'
V26_SOURCE_TREE = '78d817c2c3639484b49189bbf3bbea4dcaf8161b'
V26_PATCH_SHA = '78629c1c34c0e5c2dca4e4e1aac5edd477b45021eb91589757d3e72b6e6bdd69'
V27_SOURCE_COMMIT = '824d5b2d50a72c3def254d579eadf6a265dcee4b'
V27_SOURCE_TREE = 'e3749090d3c87d3e78b831149782dd5fc5aeccc3'
V27_PATCH_SHA = 'ffd9488fad78d81d8e4e382cd8a7c7f542fb9d9cb5a585ebc204d76f9b39575f'
# Actual raw mode/blob/status/path entries of the existing V21 parity layer.
# V22/V23 change sub/video/test only; these 19 existing entries must stay exact.
ATMOS_ENTRIES = '''
:100644 100644 61d3a038e75a28fdf40ec229b2c38f98d8ee8c16 e4ba143f08d0db572d82ddf2ac05f777ad9b44b8 M\tCopyright
:000000 100644 0000000000000000000000000000000000000000 1c9591aeb4b3ec8157a89454d3951c4d6467568e A\taudio/decode/ad_orender.c
:000000 100644 0000000000000000000000000000000000000000 d9db0d616a1c9d73c049094f6fb2a689d72833b4 A\taudio/decode/ad_orender.h
:100644 100644 4e5e9e3df7942f3a2a1385446db9fa514862a344 1c110064dc72ca4def3815f131a1c07085b21018 M\taudio/out/ao.c
:000000 100644 0000000000000000000000000000000000000000 e1572df0f80a0b2c1e4336887a9e69c7c6b629b8 A\taudio/out/ao_asio.c
:000000 100644 0000000000000000000000000000000000000000 c3f85dcf4c99a5ccf16916e5ae52622ea2b6d9b9 A\taudio/out/ao_asio.h
:100644 100644 b8a7f40f0e437dc7dc09c9f38f9e0be09c0fa6ff 51ed4db27642c2a4dbf2afe3512822f3f776ace3 M\taudio/out/ao_wasapi_utils.c
:000000 100644 0000000000000000000000000000000000000000 927b86352975a82097c2c12eac7a4e4a335d6ada A\tcommon/orender_abi.h
:000000 100644 0000000000000000000000000000000000000000 97950d40e1236ed18f150872c5227cc1a0d8a638 A\tcommon/orender_dl.c
:000000 100644 0000000000000000000000000000000000000000 75147e639dbb0de7aa121f996e9e05c3f16bae49 A\tcommon/orender_dl.h
:100644 100644 b0f046119c0fd3b484663402ce6dbdfeffdde44d 60817e6240a391fec779b8dda14c456507e0422c M\tfilters/f_decoder_wrapper.c
:100644 100644 c2ad95a642fc9753abb8ff42e8b6cb96231a9c4b 7bb1ff5bf2c2179b66313aa7956314ffb582ae7e M\tfilters/f_decoder_wrapper.h
:100644 100644 149109b14f8c8279806c68762c1524934e6a642a 9d3533e6091319822bb7a731104b102090754561 M\tmeson.build
:100644 100644 416ee3b5edf095a4dbf21a32ec9730c96fd811a7 44a0261684c2f43c080588774d092ddd76600370 M\tmeson.options
:100644 100644 cd78c81280e386dd4b57a89284319ee8fa40e659 b28fa2f33e98b81217ffe9e2405a6d82ba0a7660 M\toptions/options.c
:100644 100644 0fa18de16485533d8da4c8b4c32fdc14b6aa4ed1 c8efaf6e6e8db07b38a5ffbf019de6f4976aec8b M\toptions/options.h
:100644 100644 099b6b206ebf9946c9caf0448ec007cd26f80538 bbc8b2dd77b2b8eed1881a8294837707608991d7 M\tplayer/core.h
:100644 100644 9fadbcdc7df9e4fb54eafb20b45405261ea04457 3398468648071fb2ac3ad59f865aff3cc84b825e M\tplayer/main.c
:000000 100644 0000000000000000000000000000000000000000 b22742e318b3221e76cfcaaaf7e73001e36f4460 A\tplayer/orender_overlay.c
'''.strip().splitlines()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(source, *arguments):
    return subprocess.check_output(['git', '-C', str(source), *arguments], text=True, timeout=30).strip()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def valid_trees(main, atmos):
    require(type(main) is str and re.fullmatch('[0-9a-f]{40}', main), 'Expected main tree must be an explicit lowercase40hex value')
    require(type(atmos) is str and re.fullmatch('[0-9a-f]{40}', atmos), 'Expected Atmos tree must be an explicit lowercase40hex value')


def exact_delta(raw):
    require(raw.strip().splitlines() == ATMOS_ENTRIES, 'Existing19 Atmos mode/blob/status/path entries changed')


def locked_v22_reference(source, main_ref, query=git):
    """Pin the actual V22 tree; source commit and replay commit stay distinct."""
    rows = query(source, 'log', '--format=%H %T', main_ref).splitlines()
    require(rows and all(re.fullmatch('[0-9a-f]{40} [0-9a-f]{40}', row) for row in rows),
            'Malformed exact replay ancestry')
    matches = [row.split()[0] for row in rows if row.split()[1] == V22_LINUX_TREE]
    require(len(matches) == 1, 'Locked V22 archive tree missing/repeated; no relative-ref fallback')
    ref = matches[0]
    require(query(source, 'rev-list', '--count', ref) == '51' and
            query(source, 'rev-parse', ref+'^{tree}') == V22_LINUX_TREE,
            'Locked V22 reference layer/tree mismatch')
    ready_ref = query(source, 'rev-parse', ref+'^')
    require(re.fullmatch('[0-9a-f]{40}', ready_ref) and
            query(source, 'rev-list', '--count', ready_ref) == '50',
            'Locked V22 parent is not the exact fifty-layer V21 readiness reference')
    return ref, ready_ref


def lock_inputs():
    lock = json.loads((HERE/'source-lock.json').read_text(encoding='utf-8'))
    require(lock['mpv_base'] == BASE_COMMIT, 'Source lock upstream base changed')
    inputs = {str((HERE/'source-lock.json').relative_to(CONFIG)):sha(HERE/'source-lock.json')}
    for key in ('patches', 'common_patches'):
        require(type(lock[key]) is dict and lock[key], 'Empty patch lock set')
        for name,digest in lock[key].items():
            path = (HERE/name if key == 'patches' else CONFIG/name).resolve()
            require(path.is_relative_to(CONFIG.resolve()) and re.fullmatch('[0-9a-f]{64}',digest), 'Invalid locked patch path/hash')
            require(sha(path) == digest, 'Locked patch changed: '+name)
            inputs[str(path.relative_to(CONFIG))] = digest
    require(sha(HERE/'mpv-9100-omniphony-parity.patch') == PARITY_SHA, 'Existing Atmos parity patch changed')
    require(sha(HERE/'verify-native-ass-integration-v22-baseline.py') == V22_REFERENCE_GATE_SHA,
            'Frozen V22 integration reference bytes changed')
    require(len([name for name in lock['common_patches'] if name.startswith('build/bluray-menu/patches/0040-')]) == 1,
            'Exactly one locked V22 0040 patch is required')
    require(lock['common_patches'].get('build/bluray-menu/patches/0040-native-ass-coherent-queue-lead.patch') == V22_PATCH_SHA,
            'Frozen V22 e882 patch provenance changed')
    require(len([name for name in lock['common_patches'] if name.startswith('build/bluray-menu/patches/0041-')]) == 1,
            'Exactly one locked V23 0041 patch is required')
    require(len([name for name in lock['common_patches'] if name.startswith('build/bluray-menu/patches/0042-')]) == 1,
            'Exactly one locked V24 0042 patch is required')
    require(lock['common_patches'].get('build/bluray-menu/patches/0042-native-ass-fixed-display-phase.patch') == V24_PATCH_SHA,
            'Frozen V24 b92 single-email patch provenance changed')
    require(lock['common_patches'].get('build/bluray-menu/patches/0043-native-ass-ui-probe-recovery.patch') == V25_PATCH_SHA,
            'V25 UI recovery patch provenance changed')
    require(lock['common_patches'].get('build/bluray-menu/patches/0044-native-ass-ui-lifecycle.patch') == V26_PATCH_SHA,
            'V26 lifecycle patch provenance changed')
    require(lock['common_patches'].get('build/bluray-menu/patches/0045-native-ass-fixed-budget-recovery.patch') == V27_PATCH_SHA,
            'V27 fixed budget recovery patch provenance changed')
    for path in (HERE/'verify-source.py', HERE/'verify-native-ass-integration.py', HERE/'verify-native-ass-integration-v26.py',
                 HERE/'verify-native-ass-integration-v22-baseline.py',
                 HERE/'verify-native-ass-queue-stage-caller.py',
                 HERE/'verify-native-ass-ui-probe.py',
                 HERE/'verify-native-ass-queue-stage-caller-v26.py',
                 HERE/'verify-native-ass-ui-probe-v26.py',
                 HERE/'verify-native-ass-sample-lifecycle.py',
                 HERE/'verify-native-ass-fixed-budget-recovery.py', Path(__file__).resolve(),
                 CONFIG/'.github/workflows/native-ass-fast-gcc-preflight.yml',
                 CONFIG/'.github/workflows/build-mpv-v100-parity.yml'):
        inputs[str(path.relative_to(CONFIG))] = sha(path)
    return inputs


def compile_only(gate, source, cc):
    inputs = {}
    def read(name):
        data = (source/name).read_bytes()
        inputs[name] = hashlib.sha256(data).hexdigest()
        return data.decode('utf-8')
    try:
        # Default complete real OSD state/getter is mandatory, never partial.
        result = gate.compile_gate(source, cc, read)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result = {'pass':False, 'error':str(error)}
    result['source_sha256'] = inputs
    return result


def execute_queue_tests(gate, source, legacy_source, baseline_ref, cc, work):
    """Run real C fixtures; registration or a compile-only result is insufficient."""
    result = {}
    for name,flags in [('ordinary',[]),('NDEBUG',['-DNDEBUG'])]:
        executable = work/('queue-pure-'+name)
        command = [str(cc),'-std=c99','-O2','-Wall','-Werror',*flags,
                   '-I'+str(source),str(source/'test/secondary_ass_queue_lead.c'),
                   '-lm','-o',str(executable)]
        compiled = subprocess.run(command,text=True,capture_output=True,timeout=30)
        require(compiled.returncode == 0, 'Pure actual GCC fixture failed: '+compiled.stderr)
        executed = subprocess.run([str(executable)],text=True,capture_output=True,timeout=30)
        require(executed.returncode == 0, 'Pure actual GCC execution failed: '+executed.stderr)
        measured = json.loads(executed.stdout)
        require(measured == {'checks':149,'passed':True}, 'Pure fixture execution/count mismatch')
        result[name] = {'command':command,'result':measured,
                        'source_sha256':sha(source/'test/secondary_ass_queue_lead.c')}
    # The original controlled 6076 fixture remains exact at V22. The current
    # V23 complete declaration/OSD/caller gates independently test new code.
    script = legacy_source/'test/queue_lead_actual_review.py'
    nodes = ast.parse(script.read_text(encoding='utf-8'))
    body = []
    for node in nodes.body:
        names = {target.id for target in node.targets if isinstance(target,ast.Name)} if isinstance(node,ast.Assign) else set()
        if 'ROOT' in names:
            node.value = ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(legacy_source))],keywords=[])
        elif 'OUT' in names:
            node.value = ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(work))],keywords=[])
        elif 'original_ready' in names:
            node.value = ast.parse("extract(baseline_vo, 'bool vo_is_ready_for_frame(').replace('vo_is_ready_for_frame(', 'vo_is_ready_original(', 1)",mode='eval').body
        body.append(node)
        if 'c' in names:
            break
    require('c' in names, 'Actual caller fixture construction not found')
    baseline_vo = subprocess.check_output(['git','-C',str(legacy_source),'show',baseline_ref+':video/out/vo.c'],text=True,timeout=30)
    namespace = {'__file__':str(script),'baseline_vo':baseline_vo}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(script),'exec'),namespace)
    c = namespace['c']
    actual_file = work/'queue-actual.c'
    actual_file.write_text(c,encoding='utf-8',newline='\n')
    executable = work/'queue-actual'
    command = [str(cc),'-std=c99','-O2','-I'+str(legacy_source),str(actual_file),'-lm','-o',str(executable)]
    compiled = subprocess.run(command,text=True,capture_output=True,timeout=30)
    require(compiled.returncode == 0, 'Actual caller GCC fixture failed: '+compiled.stderr)
    executed = subprocess.run([str(executable)],text=True,capture_output=True,timeout=30)
    require(executed.returncode == 0, 'Actual caller GCC execution failed: '+executed.stderr)
    measured = json.loads(executed.stdout)
    require(measured['passed'] and measured['checks'] == 6076, 'Actual caller executed check count mismatch')
    require(measured['feedback_coverage'] == [
        {'rate':rate,'samples':64,'canonical':64,'same_lattice':64,'old_literal_guard_eligible':0,
         'candidate_eligible':0 if rate <=120 else 64}
        for rate in (60,120,144,165,240,360)], 'Actual continuous feedback eligibility mismatch')
    result['actual_caller'] = {'command':command,'result':measured,
        'source_sha256':sha(script),'generated_C_sha256':sha(actual_file),
        'baseline_vo_sha256':hashlib.sha256(baseline_vo.encode()).hexdigest(),
        'reference_commit':git(legacy_source,'rev-parse','HEAD'),
        'reference_tree':git(legacy_source,'rev-parse','HEAD^{tree}'),
        'original_ready_reference':baseline_ref,
        'scope':'LEGACY_REFERENCE_REGRESSION_NOT_V23_CALLER_NOT_DISPLAY_ACCEPTANCE'}
    return result


FORECAST_PURE_CASES = (
    ('secondary_ass_queue_stage.c', 'secondary_ass_queue_stage: 292 checks passed', 292, None),
    ('secondary_ass_stage_prefix.c', 'secondary_ass_stage_prefix: 87529 checks, 5894 feedback frames passed', 87529, 5894),
    ('secondary_ass_display_forecast.c', 'display-forecast: 59483690 checks; 2148322 complete feedback frames; CPU only', 59483690, 2148322),
    ('secondary_ass_fixed_forecast.c', '{"checks":5567,"feedback_frames":240,"historical_changes":40,"cpu_only":true,"Display_PASS":false}', 5567, 240),
)


def execute_forecast_tests(gate, source, cc, work):
    """Execute the actual headers and registered fixtures in both assert modes."""
    meson = gate.meson_uncomment((source/'test/meson.build').read_text(encoding='utf-8'))
    result = {}
    for filename, expected, checks, feedback_frames in FORECAST_PURE_CASES:
        stem = Path(filename).stem
        target = stem.replace('_', '-')
        require(len(re.findall(r"\bexecutable\s*\(\s*'"+re.escape(target)+"'", meson)) == 1 and
                len(re.findall(r"\btest\s*\(\s*'"+re.escape(target)+"'", meson)) == 1 and
                meson.count("'"+filename+"'") == 1,
                'New pure fixture must be registered once in actual test/meson.build: '+filename)
        test_source = source/'test'/filename
        inputs = {name:sha(source/name) for name in gate.HEADERS}
        inputs['test/'+filename] = sha(test_source)
        inputs['test/meson.build'] = sha(source/'test/meson.build')
        modes = {}
        for name, flags in [('ordinary', []), ('NDEBUG', ['-DNDEBUG'])]:
            executable = work/(stem+'-'+name)
            command = [str(cc), '-std=c99', '-O2', '-Wall', '-Werror', *flags,
                       '-I'+str(source), str(test_source), '-lm', '-o', str(executable)]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=60)
            require(compiled.returncode == 0, 'New actual C fixture compile failed: '+filename+' '+compiled.stderr)
            executed = subprocess.run([str(executable)], text=True, capture_output=True, timeout=60)
            require(executed.returncode == 0 and executed.stdout.strip() == expected,
                    'New actual C fixture execution/count mismatch: '+filename+' '+executed.stdout+' '+executed.stderr)
            modes[name] = {'command':command, 'compile_returncode':compiled.returncode,
                           'execute_returncode':executed.returncode, 'stdout':executed.stdout,
                           'checks':checks, 'complete_feedback_frames':feedback_frames,
                           'executable_sha256':sha(executable)}
        require(all(sha(source/path) == digest for path, digest in inputs.items()),
                'New fixture source changed during execution: '+filename)
        result[stem] = {'modes':modes, 'source_sha256':inputs,
                       'scope':'ACTUAL_C_CPU_MODEL_NOT_DISPLAY_OR_FRAME_PACING_ACCEPTANCE'}
    return result


def execute_stage_caller(source, baseline, cc, work):
    """Replay actual VO queue/promotion/outer fragments, not mirror structs."""
    tool = HERE/'verify-native-ass-queue-stage-caller-v26.py'
    output = work/'stage-actual'
    command = [sys.executable, str(tool), '--source', str(source), '--baseline', str(baseline),
               '--cc', str(cc), '--output', str(output), '--mutants',
               '--gate', str(HERE/'verify-native-ass-integration-v22-baseline.py')]
    executed = subprocess.run(command, text=True, capture_output=True, timeout=600)
    require(executed.returncode == 0, 'Actual VO stage caller execution failed: '+executed.stdout+' '+executed.stderr)
    proof = output/'actual-C-evidence.json'
    measured = json.loads(proof.read_text(encoding='utf-8'))
    require(measured.get('status') == 'ACTUAL_VO_CPU_BOUNDARY_PASS_NOT_RUNTIME' and
            measured.get('GPU_started') is False and measured.get('CI_started') is False and
            measured.get('OSD_getter_actual_body_compiled') is False and
            not measured.get('inputs_changed_during_run'), 'Actual VO stage boundary/scope mismatch')
    modes = measured.get('actual_C', {})
    require(set(modes) == {'normal', 'NDEBUG'}, 'Actual VO stage assert-mode coverage missing')
    for mode, item in modes.items():
        result = item.get('result', {})
        require(item.get('compiled') is True and item.get('compile_returncode') == 0 and
                item.get('exit_code') == 0 and result.get('checks') == 103149 and
                result.get('v24_checks') == 1097 and
                result.get('failures') == 0 and result.get('actual_feedback_frames') == 312 and
                result.get('early_prepare_positive') == 12,
                'Actual VO stage positive execution/count mismatch: '+mode)
    mutants = measured.get('mutants', {})
    require(len(mutants) == 15 and all(item.get('compiled') is True and
            item.get('compile_returncode') == 0 and item.get('compiled_and_rejected') is True
            for item in mutants.values()), 'Actual VO stage fifteen runtime mutants did not compile and reject')
    fixed_mutants = measured.get('v24_mutants', {})
    require(len(fixed_mutants) == 5 and all(item.get('compiled') is True and
            item.get('compile_returncode') == 0 and item.get('compiled_and_rejected') is True
            for item in fixed_mutants.values()), 'Actual V24 probe/hold/fixed-offset faults did not compile and reject')
    return {'command':command, 'evidence_path':str(proof.relative_to(work)),
            'evidence_sha256':sha(proof), 'tool_sha256':sha(tool),
            'actual_C':modes, 'mutants':mutants, 'v24_mutants':fixed_mutants,
            'source_sha256':measured['source_sha256'],
            'scope':measured['scope'], 'OSD_getter_actual_body_compiled':False,
            'not_covered':measured['not_covered']}


def replace_once(folder, name, old, new):
    path = folder/name
    text = path.read_text(encoding='utf-8')
    require(text.count(old) == 1, 'Mutation anchor is not unique: '+name)
    path.write_text(text.replace(old,new,1), encoding='utf-8', newline='\n')


def function_mutation(gate, folder, path, name, modify):
    text = (folder/path).read_text(encoding='utf-8')
    actual = gate.functions(text)[name]['text']
    changed = modify(actual)
    require(changed != actual, 'Function mutation did not change actual source')
    replace_once(folder,path,actual,changed)


def negative_matrix(gate, source, cc, work):
    paths = list(dict.fromkeys(list(gate.HEADERS)+[
        'video/out/vo.h','video/out/vo.c','video/out/vo_gpu_next.c','video/out/d3d11/context.c',
        'sub/osd.h','sub/osd.c','sub/osd_state.h','osdep/threads-win32.h','osdep/timer.h',
        'common/common.h','misc/mp_assert.h']))
    cases = [
        ('missing_source_queue_include','video/out/vo.c','#include "secondary_ass_queue_lead.h"',''),
        ('missing_snapshot_prototype','sub/osd.h','struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(struct osd_state *osd);',''),
        ('wrong_snapshot_arity','sub/osd.h','struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(struct osd_state *osd);',
         'struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(struct osd_state *osd, int extra);'),
        ('wrong_snapshot_return','sub/osd.h','struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(struct osd_state *osd);',
         'bool osd_get_secondary_sample_snapshot(struct osd_state *osd);'),
        ('queue_token_field_missing','video/out/secondary_ass_queue_lead.h','int64_t fresh_due, old_lead, old_admission, admission;',
         'int64_t fresh_due, old_lead, old_admission, missing_admission;'),
        ('hint_publisher_wrong_field','video/out/vo.c','hint.retained_id = in->current_frame->frame_id;',
         'hint.no_such_field = in->current_frame->frame_id;'),
        ('wrong_current_call_arity','video/out/vo.c','in->frame_queued->pts - in->flip_queue_offset,\n                in->secondary_redraw_cost);',
         'in->frame_queued->pts - in->flip_queue_offset,\n                in->secondary_redraw_cost, 1);'),
        ('missing_publisher_invocation','video/out/vo.c','        secondary_publish_queue_hint(vo);',''),
    ]
    labels = [row[0] for row in cases]+['missing_queue_header','missing_snapshot_definition','missing_hint_definition',
        'missing_snapshot_struct','getter_osd_field_missing','getter_sampler_field_missing','getter_definition_arity']
    results = []
    for label in labels:
        folder = work/label
        folder.mkdir()
        for name in paths:
            destination=folder/name;destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes((source/name).read_bytes())
        if label in [row[0] for row in cases]:
            _,name,old,new = next(row for row in cases if row[0] == label)
            replace_once(folder,name,old,new)
        elif label == 'missing_queue_header':
            path=(folder/'video/out/secondary_ass_queue_lead.h').resolve()
            require(path.is_relative_to(work.resolve()), 'Deletion escaped mutation root')
            path.unlink()
        elif label in ('missing_snapshot_definition','missing_hint_definition'):
            path,name = ('sub/osd.c','osd_get_secondary_sample_snapshot') if label == 'missing_snapshot_definition' else (
                'video/out/vo.c','secondary_publish_queue_hint')
            function_mutation(gate,folder,path,name,lambda actual:'')
        elif label == 'missing_snapshot_struct':
            path='sub/secondary_ass_clock.h'
            actual,_=gate.declaration((folder/path).read_text(encoding='utf-8'),'secondary_ass_sample_snapshot')
            replace_once(folder,path,actual,'')
        elif label == 'getter_osd_field_missing':
            function_mutation(gate,folder,'sub/osd.c','osd_get_secondary_sample_snapshot',
                lambda actual:actual.replace('osd->secondary_sample_held','osd->missing_sample_held',1))
        elif label == 'getter_sampler_field_missing':
            function_mutation(gate,folder,'sub/osd.c','osd_get_secondary_sample_snapshot',
                lambda actual:actual.replace('s->force','s->missing_force',1))
        elif label == 'getter_definition_arity':
            function_mutation(gate,folder,'sub/osd.c','osd_get_secondary_sample_snapshot',
                lambda actual:actual.replace('(struct osd_state *osd)','(struct osd_state *osd, int mismatch)',1))
        result=compile_only(gate,folder,cc)
        results.append({'name':label,'expected':'FAIL','rejected':result['pass'] is False,
            'compiler_returncode':result.get('returncode'),'error':result.get('error'),
            'diagnostics':result.get('diagnostics','')[-6000:]})
    require(all(row['rejected'] for row in results), 'A mandatory source/prototype/body mutation was not rejected')
    return results


def self_test():
    valid_trees('a'*40,'b'*40)
    checks=1
    for bad in ('',None,True,'UNKNOWN','a'*39,'g'*40,'A'*40,'a'*40+';'):
        for pair in ((bad,'b'*40),('a'*40,bad)):
            try: valid_trees(*pair)
            except ValueError: checks+=1
            else: raise ValueError('Invalid explicit tree accepted')
    exact_delta('\n'.join(ATMOS_ENTRIES))
    for altered in (ATMOS_ENTRIES[:-1],ATMOS_ENTRIES+['extra'],[ATMOS_ENTRIES[0].replace('100644','100755',1)]+ATMOS_ENTRIES[1:]):
        try: exact_delta('\n'.join(altered))
        except ValueError: checks+=1
        else: raise ValueError('Changed Atmos entry accepted')
    ref,ready='c'*40,'d'*40
    answers={('log','--format=%H %T','a'*40):ref+' '+V22_LINUX_TREE,
             ('rev-list','--count',ref):'51',('rev-parse',ref+'^{tree}'):V22_LINUX_TREE,
             ('rev-parse',ref+'^'):ready,('rev-list','--count',ready):'50'}
    def query(_source,*args):
        return answers[args]
    require(locked_v22_reference(None,'a'*40,query) == (ref,ready), 'Exact V22 selector failed')
    checks+=1
    defects=[(('log','--format=%H %T','a'*40),'a'*40+' '+'b'*40),
             (('log','--format=%H %T','a'*40),(ref+' '+V22_LINUX_TREE+'\n')*2),
             (('log','--format=%H %T','a'*40),'UNKNOWN'),
             (('rev-list','--count',ref),'52'),
             (('rev-parse',ref+'^{tree}'),'e'*40),
             (('rev-parse',ref+'^'),'UNKNOWN'),
             (('rev-list','--count',ready),'51')]
    for key,bad in defects:
        original=answers[key];answers[key]=bad
        try:
            locked_v22_reference(None,'a'*40,query)
        except ValueError:
            checks+=1
        else:
            raise ValueError('Foreign/drifting V22 selector input accepted')
        finally:
            answers[key]=original
    print(json.dumps({'status':'CPU_INPUT_REFUSAL_SELF_TEST_PASS','checks':checks,'gpu_started':False}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--work',type=Path)
    parser.add_argument('--cc',type=Path)
    parser.add_argument('--expected-main-tree')
    parser.add_argument('--expected-atmos-tree')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--validate-inputs',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        self_test();return 0
    valid_trees(args.expected_main_tree,args.expected_atmos_tree)
    if args.validate_inputs:
        print(json.dumps({'status':'EXPLICIT_TREE_INPUT_FORMAT_PASS_SOURCE_IDENTITY_NOT_YET_VERIFIED','gpu_started':False}))
        return 0
    require(all((args.source,args.archive,args.work,args.cc)), 'Source/archive/newwork/GCC must be explicit')
    source,work,cc=args.source.resolve(),args.work.resolve(),args.cc.resolve()
    require(not work.exists() and source.is_dir() and cc.is_file(), 'New private work/source/compiler boundary invalid')
    work.mkdir(parents=True)
    report={'status':'FAST_GCC_PREFLIGHT_STARTED_NOT_CORE_BUILD_OR_RUNTIME','gpu_started':False,
        'full_core_build_started':False,'full_build_verified':False,'runtime_verified':False,
        'deployment_allowed':False,'pacing_acceptance_granted':False,'production_changed':False,
        'expected_main_tree':args.expected_main_tree,'expected_atmos_tree':args.expected_atmos_tree,
        'baseline_parity_gate_sha256':BASELINE_GATE_SHA,'positive_variants':{},'negative_variants':{}}
    try:
        require(sha(args.archive) == ARCHIVE_SHA, 'Exact upstream archive SHA mismatch')
        inputs=lock_inputs();report['config_inputs_sha256']=inputs
        require(git(source,'status','--porcelain') == '', 'Fresh replay is dirty')
        require(git(source,'rev-list','--count','HEAD') == '57', 'Exact V27 replay must contain57 Git layers')
        require(git(source,'rev-list','--count','HEAD^') == '56', 'Exact main replay must contain56 Git layers')
        require('Add current Omniphony renderer and ASIO' in git(source,'log','-1','--format=%s'), 'Last layer is not existing Atmos parity')
        main_ref,atmos_ref=git(source,'rev-parse','HEAD^'),git(source,'rev-parse','HEAD')
        main_tree,atmos_tree=git(source,'rev-parse',main_ref+'^{tree}'),git(source,'rev-parse',atmos_ref+'^{tree}')
        report['observed_replay'] = {'main_commit':main_ref,'main_tree':main_tree,
            'atmos_commit':atmos_ref,'atmos_tree':atmos_tree}
        require(main_tree == args.expected_main_tree and atmos_tree == args.expected_atmos_tree, 'Unknown/unexpected exact replay tree')
        delta=git(source,'diff','--raw','--no-abbrev','HEAD^','HEAD')
        exact_delta(delta)
        report['replay']={'main_commit':main_ref,'main_tree':main_tree,'atmos_commit':atmos_ref,'atmos_tree':atmos_tree,
            'commit_count':57,'exact_existing19_atmos_entries':delta.splitlines(),'archive_sha256':ARCHIVE_SHA}
        report['candidate_source_provenance'] = {'commit':V27_SOURCE_COMMIT,
            'windows_tree':V27_SOURCE_TREE, 'incremental_patch_sha256':V27_PATCH_SHA,
            'frozen_v26_parent_commit':V26_SOURCE_COMMIT, 'frozen_v26_parent_tree':V26_SOURCE_TREE,
            'replay_commit_metadata_equal_to_author_commit':False}
        version=subprocess.check_output([str(cc),'--version'],text=True,timeout=15)
        require(re.search(r'\b(?:gcc|GCC)\b',version), 'Fast preflight requires actual GCC, never TCC partial')
        report['compiler']={'path':str(cc),'version':version,'sha256':sha(cc)}
        spec=importlib.util.spec_from_file_location('native_ass_default_gcc_gate',HERE/'verify-native-ass-integration-v26.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        legacy_ref,legacy_ready_ref=locked_v22_reference(source,main_ref)
        legacy_root=work/'legacy-reference-v22'
        subprocess.run(['git','-C',str(source),'worktree','add','--detach',str(legacy_root),legacy_ref],
                       check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
        require(git(legacy_root,'rev-list','--count','HEAD') == '51' and not git(legacy_root,'status','--porcelain'),
                'Legacy V22 reference must contain exactly51 layers and be clean')
        report['legacy_reference']={'commit':git(legacy_root,'rev-parse','HEAD'),
                                    'tree':git(legacy_root,'rev-parse','HEAD^{tree}'),
                                    'source_provenance_commit':V22_SOURCE_COMMIT,
                                    'locked_0040_sha256':V22_PATCH_SHA,
                                    'V21_original_ready_reference':legacy_ready_ref,
                                    'scope':'LEGACY_REFERENCE_REGRESSION_NOT_V23_CALLER'}
        for variant,ref in [('main',main_ref),('atmos',atmos_ref)]:
            variant_root=work/variant
            subprocess.run(['git','-C',str(source),'worktree','add','--detach',str(variant_root),ref],check=True,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
            evidence={}
            def read(name):
                data=(variant_root/name).read_bytes();evidence[name]=hashlib.sha256(data).hexdigest();return data.decode('utf-8')
            meson=gate.meson_check(variant_root,variant,read)
            compile_result=gate.compile_gate(variant_root,cc,read,
                                            output_translation=work/(variant+'-real-osd-vo.c'))
            positive={'meson':meson,'compile':compile_result,'source_sha256':evidence}
            report['positive_variants'][variant]=positive;write(work/('positive-'+variant+'.json'),positive)
            require(meson['pass'] and compile_result['pass'] and compile_result.get('queue_osd_getter_compiled') is True,
                'Default full real OSD/VO GCC positive failed: '+variant)
            require(any(row.get('struct') == 'osd_state' for row in compile_result['real_complete_structs']) and
                any(row.get('function') == 'osd_get_secondary_sample_snapshot' and row.get('file') == 'sub/osd.c'
                    for row in compile_result['verbatim_full_functions']), 'Actual complete OSD/getter closure was skipped')
            actual_forecast = compile_result.get('cpu_forecast_caller_execution', {})
            require(actual_forecast.get('pass') is True and len(actual_forecast.get('cases', {})) == 8,
                    'Current complete forecast caller positive/seven runtime mutants did not execute: '+variant)
            require(len(actual_forecast.get('v24_cases', {})) == 7 and
                    actual_forecast.get('positive_NDEBUG', {}).get('pass') is True,
                    'Actual V24 fixed flag/CONFIG/selection/reset runtime cases did not execute: '+variant)
            for positive_mode in (actual_forecast['cases']['positive'], actual_forecast['positive_NDEBUG']):
                require(positive_mode.get('result') == {
                    'original_legacy_checks':7520, 'new_clock_getter_checks':896,
                    'new_sampler_snapshot_checks':952, 'actual_caller_checks':16657, 'legacy_caller_checks':9368,
                    'fixed_caller_checks':7289, 'passed':True, 'GPU':False},
                    'Actual V24 current caller count/near-expiry boundary did not execute: '+variant)
            test_work = work/('queue-tests-'+variant)
            test_work.mkdir()
            positive['executed_queue_tests'] = execute_queue_tests(gate,variant_root,legacy_root,legacy_ready_ref,cc,test_work)
            forecast_work = work/('forecast-tests-'+variant)
            forecast_work.mkdir()
            positive['executed_forecast_tests'] = execute_forecast_tests(gate, variant_root, cc, forecast_work)
            positive['executed_stage_caller'] = execute_stage_caller(variant_root, legacy_root, cc, forecast_work)
            ui_output = work/('ui-probe-'+variant)
            ui_run = subprocess.run([sys.executable,str(HERE/'verify-native-ass-ui-probe-v26.py'),
                '--source',str(variant_root),'--baseline',str(legacy_root),'--cc',str(cc),
                '--output',str(ui_output)],capture_output=True,text=True,timeout=120)
            ui_result = json.loads((ui_output/'ui-probe.json').read_text(encoding='utf-8'))
            positive['executed_ui_probe'] = {'returncode':ui_run.returncode,
                'stdout':ui_run.stdout,'stderr':ui_run.stderr,'report':ui_result}
            require(ui_run.returncode == 0 and ui_result['status'] == 'PASS_CPU_NOT_GPU',
                    'Actual V26 UI probe tail/outer scheduler failed: '+variant)
            lifecycle_out = work/('sample-lifecycle-'+variant)
            lifecycle_run = subprocess.run([sys.executable,str(HERE/'verify-native-ass-sample-lifecycle.py'),
                '--source',str(variant_root),'--cc',str(cc),'--output',str(lifecycle_out)],
                capture_output=True,text=True,timeout=120)
            lifecycle = json.loads((lifecycle_out/'report.json').read_bytes())
            require(lifecycle_run.returncode == 0 and lifecycle['status'] == 'PASS_CPU_NOT_RUNTIME',
                    'Actual sampler epoch lifecycle failed: '+variant)
            require(set(lifecycle['cases']) == {'candidate-normal','candidate-NDEBUG',
                    'old_epoch_projection_fault-normal','old_epoch_projection_fault-NDEBUG'},
                    'Epoch lifecycle modes/fault missing')
            for name,item in lifecycle['cases'].items():
                require(item['compile_exit'] == 0 and item['exit'] == (0 if name.startswith('candidate') else 7)
                    and item['stdout'] == ('checks=3612 failures=0\n' if name.startswith('candidate')
                        else 'checks=3612 failures=1032\n'), 'Epoch lifecycle exact counter mismatch')
            positive['executed_sample_lifecycle'] = {'report':lifecycle,
                'report_sha256':sha(lifecycle_out/'report.json')}
            recovery_out = work/('fixed-budget-recovery-'+variant)
            recovery_run = subprocess.run([sys.executable,str(HERE/'verify-native-ass-fixed-budget-recovery.py'),
                '--source',str(variant_root),'--baseline',str(legacy_root),'--cc',str(cc),
                '--output',str(recovery_out)],capture_output=True,text=True,timeout=180)
            recovery = json.loads((recovery_out/'fixed-budget-recovery.json').read_bytes())
            require(recovery_run.returncode == 0 and
                    recovery['status'] == 'ACTUAL_FIXED_BUDGET_RECOVERY_CPU_PASS_NOT_RUNTIME',
                    'Actual fixed budget recovery failed: '+variant+' '+recovery_run.stderr[-1000:])
            expected_cases = {name+'_'+mode for name in ('positive','outer_eligibility_omitted',
                'redraw_eligibility_omitted','fixed_recovery_bit_omitted','fixed_scope_lost',
                'margin_lost','cooldown_lost','overload_lost') for mode in ('normal','NDEBUG')}
            require(set(recovery['cases']) == expected_cases and
                all(item['compiled_and_expected'] for item in recovery['cases'].values()),
                'Recovery positive/fault modes missing or did not compile and execute')
            for mode in ('normal','NDEBUG'):
                item = recovery['cases']['positive_'+mode]
                require(item['compiled'] and item['compile_returncode'] == 0 and item['exit_code'] == 0 and
                    item['result']['checks'] == 103149 and item['result']['v24_checks'] == 1097 and
                    item['new_result'] == {'checks':3801,'grids':57,'failures':0},
                    'Actual recovery counts/compiler boundary changed')
            require(not recovery['inputs_changed_during_run'] and not recovery['baseline_changed_during_run'],
                    'Recovery input changed during execution')
            positive['executed_fixed_budget_recovery'] = {'returncode':recovery_run.returncode,
                'stdout':recovery_run.stdout,'stderr':recovery_run.stderr,'report':recovery,
                'report_sha256':sha(recovery_out/'fixed-budget-recovery.json')}
            write(work/('positive-'+variant+'.json'),positive)
            mutation_root=work/('mutations-'+variant);mutation_root.mkdir()
            report['negative_variants'][variant]=negative_matrix(gate,variant_root,cc,mutation_root)
            require(not git(variant_root,'status','--porcelain'), 'Negative matrix changed original variant worktree')
        for name,digest in inputs.items():
            require(sha(CONFIG/name) == digest, 'Config input changed during fast preflight: '+name)
        require(not git(source,'status','--porcelain'), 'Original replay changed during preflight')
        require(not git(legacy_root,'status','--porcelain'), 'Legacy V22 reference changed during preflight')
        report.update(status='EXACT_V27_REPLAY_DUAL_DEFAULT_GCC_POSITIVE_AND_NEGATIVE_PASS_NOT_CORE_BUILD_OR_RUNTIME',
            full_osd_getter_gcc_verified=True,negative_count_per_variant=15)
        return 0
    except BaseException as error:
        report.update(status='FAST_GCC_PREFLIGHT_FAIL_NO_CORE_BUILD_OR_GPU',error_type=type(error).__name__,error=str(error))
        return 1
    finally:
        write(work/'fast-preflight.json',report)
        print(json.dumps({'status':report['status'],'error':report.get('error'),'gpu_started':False,
                          'full_core_build_started':False}))


if __name__ == '__main__':
    raise SystemExit(main())
