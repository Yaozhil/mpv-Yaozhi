"""Exercise real Git source-layer acceptance/refusal without a player or GPU."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_refresh_gate', HERE/'verify-native-refresh-source.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def git(source, *args):
    return gate.command(['git', '-C', source, '-c', 'core.autocrlf=false',
        '-c', 'user.name=Source gate fixture', '-c', 'user.email=fixture@localhost', *args])


def write(root, relative, raw):
    target = root/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    checks = []
    with tempfile.TemporaryDirectory(prefix='native-refresh-gate-fixture-') as folder:
        root = Path(folder)
        source, config = root/'source', root/'config'
        source.mkdir(); config.mkdir()
        for path in (source, config):
            git(path, 'init', '--quiet')
        write(source, 'video/out/vo.c', b'int original = 1;\n')
        write(source, 'unchanged.txt', b'Keep this byte exact.\n')
        git(source, 'add', '.'); git(source, 'commit', '--quiet', '-m', 'Frozen parent')
        baseline = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
        before = gate.sha((source/'video/out/vo.c').read_bytes())
        write(source, 'video/out/vo.c', b'int fixed = 2;\n')
        write(source, 'video/out/secondary_ass_fresh_video.h', b'int helper = 3;\n')
        git(source, 'add', '.'); git(source, 'commit', '--quiet', '-m', 'Approved native refresh')
        final = git(source, 'rev-parse', 'HEAD').decode().strip()
        final_tree = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
        patch = write(config, 'native-refresh.patch', git(source, 'format-patch', '-1', '--stdout'))
        for relative in ('build/atmos/parity/source-lock.json', 'build/atmos/parity/dependency-lock.json'):
            write(config, relative, (gate.CONFIG/relative).read_bytes())
        for relative in gate.REQUIRED_TOOLS:
            write(config, relative, b'exact gate fixture tool\n')
        expected = dict(baseline_tree=baseline, source_tree=final_tree,
            before_source_sha256={'video/out/vo.c': before, 'video/out/secondary_ass_fresh_video.h': None},
            source_sha256={r:gate.sha((source/r).read_bytes()) for r in gate.SOURCE_FILES})
        lock = dict(version=1, parent_config_commit=gate.BASELINE_CONFIG,
            parent_config_tree=gate.BASELINE_CONFIG_TREE,
            parent_source_lock_sha256=gate.BASELINE_LOCK,
            dependency_lock_sha256=gate.BASELINE_DEPENDENCY_LOCK,
            patch=dict(path=patch.name, sha256=gate.sha(patch.read_bytes()), changed_files=list(gate.SOURCE_FILES)),
            variants=dict(main=copy.deepcopy(expected), atmos=copy.deepcopy(expected)),
            tools_sha256={p: gate.sha((config/p).read_bytes()) for p in gate.REQUIRED_TOOLS})

        def check(name, callback, refused=None):
            try:
                result = callback()
            except ValueError as error:
                if refused is None or refused not in str(error):
                    raise
                checks.append(dict(case=name, passed=True, refusal=str(error)))
                return
            if refused is not None:
                raise AssertionError('Unexpected acceptance: '+name)
            checks.append(dict(case=name, passed=True))
            return result

        def verify(value=None, **kwargs):
            return gate.verify(source, 'main', lock if value is None else value, config=config, **kwargs)

        check('Exact main complete-tree and patch replay', verify)
        check('Exact Atmos identity', lambda: gate.verify(source, 'atmos', lock, config=config))
        assert git(source, 'rev-parse', 'HEAD').decode().strip() == final and not git(source, 'status', '--porcelain').strip()
        checks.append(dict(case='Real source HEAD/index/worktree unchanged', passed=True))
        exe, com = write(root, 'mpv.exe', b'fixture-exe'), write(root, 'mpv.com', b'fixture-com')
        bound = check('Exact two produced artifact digest binding', lambda: verify(binaries=[exe, com]))
        assert bound['bound_binary_artifacts'][0]['sha256'] == gate.sha(exe.read_bytes())
        assert bound['runtime_verified'] is False and bound['performance_verified'] is False
        check('Missing compiled file', lambda: verify(binaries=[root/'missing.exe']), 'Missing compiled artifact')
        check('Duplicate compiled file', lambda: verify(binaries=[exe, exe]), 'Duplicate compiled artifact')
        check('Compiled mode requires frozen parent verification', lambda: verify(compiled=True, binaries=[exe, com]),
              'Compiled gate requires frozen parent verification')
        write(source, 'unchanged.txt', b'dirty\n')
        check('Dirty tracked byte', verify, 'Final mpv source must be completely clean')
        git(source, 'checkout', '--', 'unchanged.txt')
        write(source, 'unexpected.txt', b'untracked\n')
        check('Untracked extra source', verify, 'Final mpv source must be completely clean')
        (source/'unexpected.txt').unlink()
        for field, error in (('baseline_tree', 'parent tree'), ('source_tree', 'final tree')):
            value = copy.deepcopy(lock); value['variants']['main'][field] = '0'*40
            check('Wrong '+field, lambda v=value: verify(v), error)
        value = copy.deepcopy(lock); value['variants']['main']['source_tree'] = 'TODO'
        check('Unfrozen placeholder identity', lambda: verify(value), 'Invalid complete source tree')
        for field, error in (('before_source_sha256', 'Baseline source mismatch'),
                             ('source_sha256', 'Final source mismatch')):
            value = copy.deepcopy(lock); value['variants']['main'][field]['video/out/vo.c'] = '0'*64
            check('Wrong '+field, lambda v=value: verify(v), error)
        value = copy.deepcopy(lock); del value['variants']['atmos']
        check('Missing Atmos variant', lambda: verify(value), 'Both exact variant identities')
        value = copy.deepcopy(lock); value['patch']['changed_files'].append('unchanged.txt')
        check('Expanded declared patch scope', lambda: verify(value), 'Unexpected approved source scope')
        value = copy.deepcopy(lock); value['tools_sha256'] = {}
        check('Missing tool identity set', lambda: verify(value), 'Exact complete new tool identities')
        value = copy.deepcopy(lock); value['patch']['sha256'] = '0'*64
        check('Changed packaged patch', lambda: verify(value), 'Input digest mismatch')
        raw = patch.read_bytes()
        patch.write_bytes(raw.replace(b'int fixed = 2;', b'int fixed = 3;'))
        value = copy.deepcopy(lock); value['patch']['sha256'] = gate.sha(patch.read_bytes())
        check('Same scope altered patch content', lambda: verify(value), 'Final tree differs from packaged patch replay')
        patch.write_bytes(raw)
        original_lock = (config/'build/atmos/parity/source-lock.json').read_bytes()
        write(config, 'build/atmos/parity/source-lock.json', original_lock+b'\n')
        check('Historical source lock drift', verify, 'Input digest mismatch')
        write(config, 'build/atmos/parity/source-lock.json', original_lock)
        original_dep = (config/'build/atmos/parity/dependency-lock.json').read_bytes()
        write(config, 'build/atmos/parity/dependency-lock.json', original_dep+b'\n')
        check('Dependency generation drift', verify, 'Input digest mismatch')
        write(config, 'build/atmos/parity/dependency-lock.json', original_dep)
        value = copy.deepcopy(lock); value['parent_config_commit'] = '0'*40
        check('Wrong frozen configuration ancestor', lambda: verify(value), 'Frozen parent/dependency identity differs')
        write(source, 'unchanged.txt', b'unrelated committed edit\n')
        git(source, 'add', '.'); git(source, 'commit', '--quiet', '--amend', '--no-edit')
        value = copy.deepcopy(lock); value['variants']['main']['source_tree'] = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
        check('Complete-tree change outside approved file', lambda: verify(value), 'Unexpected appended source scope')
    result = dict(status='NATIVE_REFRESH_SOURCE_GATE_CONTRACTS_PASS', passed=True,
                  count=len(checks), checks=checks, runtime_verified=False, performance_verified=False)
    (a.output/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], count=result['count'], passed=True)))


if __name__ == '__main__':
    main()
