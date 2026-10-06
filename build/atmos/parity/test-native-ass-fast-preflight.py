"""Fast CPU GCC gate for exact V22 replay; no dependencies, SDK, GPU or core build."""
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
# Actual raw mode/blob/status/path entries of the existing V21 parity layer.
# V22 changes sub/video/test only; these 19 existing entries must stay exact.
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
    require(len([name for name in lock['common_patches'] if name.startswith('build/bluray-menu/patches/0040-')]) == 1,
            'Exactly one locked V22 0040 patch is required')
    for path in (HERE/'verify-source.py', HERE/'verify-native-ass-integration.py', Path(__file__).resolve(),
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


def execute_queue_tests(gate, source, baseline_ref, cc, work):
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
    script = source/'test/queue_lead_actual_review.py'
    nodes = ast.parse(script.read_text(encoding='utf-8'))
    body = []
    for node in nodes.body:
        names = {target.id for target in node.targets if isinstance(target,ast.Name)} if isinstance(node,ast.Assign) else set()
        if 'ROOT' in names:
            node.value = ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(source))],keywords=[])
        elif 'OUT' in names:
            node.value = ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(work))],keywords=[])
        elif 'original_ready' in names:
            node.value = ast.parse("extract(baseline_vo, 'bool vo_is_ready_for_frame(').replace('vo_is_ready_for_frame(', 'vo_is_ready_original(', 1)",mode='eval').body
        body.append(node)
        if 'c' in names:
            break
    require('c' in names, 'Actual caller fixture construction not found')
    baseline_vo = subprocess.check_output(['git','-C',str(source),'show',baseline_ref+':video/out/vo.c'],text=True,timeout=30)
    namespace = {'__file__':str(script),'baseline_vo':baseline_vo}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(script),'exec'),namespace)
    c = namespace['c']
    actual_file = work/'queue-actual.c'
    actual_file.write_text(c,encoding='utf-8',newline='\n')
    executable = work/'queue-actual'
    command = [str(cc),'-std=c99','-O2','-I'+str(source),str(actual_file),'-lm','-o',str(executable)]
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
        'scope':'Controlled CPU fixture, not full VO thread or physical Display acceptance'}
    return result


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
        require(git(source,'rev-list','--count','HEAD') == '52', 'Exact V22 replay must contain52 Git layers')
        require(git(source,'rev-list','--count','HEAD^') == '51', 'Exact main replay must contain51 Git layers')
        require('Add current Omniphony renderer and ASIO' in git(source,'log','-1','--format=%s'), 'Last layer is not existing Atmos parity')
        main_ref,atmos_ref=git(source,'rev-parse','HEAD^'),git(source,'rev-parse','HEAD')
        main_tree,atmos_tree=git(source,'rev-parse',main_ref+'^{tree}'),git(source,'rev-parse',atmos_ref+'^{tree}')
        require(main_tree == args.expected_main_tree and atmos_tree == args.expected_atmos_tree, 'Unknown/unexpected exact replay tree')
        delta=git(source,'diff','--raw','--no-abbrev','HEAD^','HEAD')
        exact_delta(delta)
        report['replay']={'main_commit':main_ref,'main_tree':main_tree,'atmos_commit':atmos_ref,'atmos_tree':atmos_tree,
            'commit_count':52,'exact_existing19_atmos_entries':delta.splitlines(),'archive_sha256':ARCHIVE_SHA}
        version=subprocess.check_output([str(cc),'--version'],text=True,timeout=15)
        require(re.search(r'\b(?:gcc|GCC)\b',version), 'Fast preflight requires actual GCC, never TCC partial')
        report['compiler']={'path':str(cc),'version':version,'sha256':sha(cc)}
        spec=importlib.util.spec_from_file_location('native_ass_default_gcc_gate',HERE/'verify-native-ass-integration.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        for variant,ref in [('main',main_ref),('atmos',atmos_ref)]:
            variant_root=work/variant
            subprocess.run(['git','-C',str(source),'worktree','add','--detach',str(variant_root),ref],check=True,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
            evidence={}
            def read(name):
                data=(variant_root/name).read_bytes();evidence[name]=hashlib.sha256(data).hexdigest();return data.decode('utf-8')
            meson=gate.meson_check(variant_root,variant,read)
            compile_result=gate.compile_gate(variant_root,cc,read)
            positive={'meson':meson,'compile':compile_result,'source_sha256':evidence}
            report['positive_variants'][variant]=positive;write(work/('positive-'+variant+'.json'),positive)
            require(meson['pass'] and compile_result['pass'] and compile_result.get('queue_osd_getter_compiled') is True,
                'Default full real OSD/VO GCC positive failed: '+variant)
            require(any(row.get('struct') == 'osd_state' for row in compile_result['real_complete_structs']) and
                any(row.get('function') == 'osd_get_secondary_sample_snapshot' and row.get('file') == 'sub/osd.c'
                    for row in compile_result['verbatim_full_functions']), 'Actual complete OSD/getter closure was skipped')
            test_work = work/('queue-tests-'+variant)
            test_work.mkdir()
            positive['executed_queue_tests'] = execute_queue_tests(gate,variant_root,main_ref+'^',cc,test_work)
            write(work/('positive-'+variant+'.json'),positive)
            mutation_root=work/('mutations-'+variant);mutation_root.mkdir()
            report['negative_variants'][variant]=negative_matrix(gate,variant_root,cc,mutation_root)
            require(not git(variant_root,'status','--porcelain'), 'Negative matrix changed original variant worktree')
        for name,digest in inputs.items():
            require(sha(CONFIG/name) == digest, 'Config input changed during fast preflight: '+name)
        require(not git(source,'status','--porcelain'), 'Original replay changed during preflight')
        report.update(status='EXACT_V22_REPLAY_DUAL_DEFAULT_GCC_POSITIVE_AND_NEGATIVE_PASS_NOT_CORE_BUILD_OR_RUNTIME',
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
