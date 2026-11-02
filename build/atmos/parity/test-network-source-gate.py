"""Exercise exact two-layer source gate acceptance and refusal contracts."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

TOOL = Path(__file__).with_name('verify-network-source.py')
spec = importlib.util.spec_from_file_location('network_gate', TOOL)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), '-c', 'core.autocrlf=false',
        '-c', 'user.name=Source gate fixture', '-c', 'user.email=fixture@localhost', *args],
        stderr=subprocess.PIPE, timeout=30).decode().strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    checks = []
    with tempfile.TemporaryDirectory(prefix='network-gate-fixture-') as folder:
        root = Path(folder)
        source, config = root/'source', root/'config'
        source.mkdir()
        config.mkdir()
        git(source, 'init', '-q')
        git(source, 'config', 'core.autocrlf', 'false')
        for i, path in enumerate(gate.SOURCE_FILES):
            target = source/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('int original_'+str(i)+' = 1;\n', encoding='utf-8')
        (source/'unchanged.txt').write_bytes(b'preserve me\n')
        git(source, 'add', '.')
        git(source, 'commit', '-qm', 'Frozen baseline')
        baseline_tree = git(source, 'rev-parse', 'HEAD^{tree}')
        before = {p: digest(source/p) for p in gate.SOURCE_FILES}
        patches, steps = [], []
        for number, scope in enumerate(gate.PATCH_SCOPES):
            for i, path in enumerate(scope):
                (source/path).write_text('int fixed_'+str(number)+'_'+str(i)+' = 2;\n', encoding='utf-8')
            git(source, 'add', '--', *scope)
            git(source, 'commit', '-qm', 'Approved layer '+str(number))
            steps.append(git(source, 'rev-parse', 'HEAD^{tree}'))
            patch = config/('layer'+str(number)+'.patch')
            patch.write_bytes((git(source, 'format-patch', '-1', '--stdout')+'\n').encode())
            patches.append(dict(path=patch.name, sha256=digest(patch), changed_files=list(scope)))
        final = git(source, 'rev-parse', 'HEAD')
        for relative in gate.REQUIRED_TOOLS:
            tool = config/relative
            tool.parent.mkdir(parents=True, exist_ok=True)
            tool.write_bytes(b'exact fixture tool identity\n')
        first_tool = sorted(gate.REQUIRED_TOOLS)[0]
        expected = dict(baseline_tree=baseline_tree, source_tree=steps[-1], step_trees=list(steps),
            archive_baseline_tree=baseline_tree, archive_source_tree=steps[-1], archive_step_trees=list(steps),
            before_source_sha256=before, source_sha256={p: digest(source/p) for p in gate.SOURCE_FILES})
        lock = dict(version=1, patches=patches,
            variants=dict(main=copy.deepcopy(expected), atmos=copy.deepcopy(expected)),
            tools_sha256={p: digest(config/p) for p in gate.REQUIRED_TOOLS})

        def check(name, operation, refusal=None):
            try:
                result = operation()
            except (ValueError, subprocess.CalledProcessError) as error:
                if refusal is None or refusal not in str(error):
                    raise
                checks.append(dict(name=name, passed=True, refused=str(error)))
                return
            if refusal is not None:
                raise AssertionError('Unexpected acceptance: '+name)
            checks.append(dict(name=name, passed=True))
            return result

        def run(value=None, **kwargs):
            return gate.verify(source, 'main', lock if value is None else value, config=config, **kwargs)

        positive = check('Exact final and both index-only replay steps', run)
        check('Independent Atmos variant identity', lambda: gate.verify(source, 'atmos', lock, config=config))
        check('Explicit archive mode', lambda: run(archive_source=True))
        assert not git(source, 'status', '--porcelain') and git(source, 'rev-parse', 'HEAD') == final
        checks.append(dict(name='Real index and worktree unchanged', passed=True))
        artifact = root/'mpv.exe'
        artifact.write_bytes(b'fixture binary identity only')
        result = check('Exact produced binary digest binding', lambda: run(binaries=[artifact]))
        assert result['bound_binary_artifacts'][0]['sha256'] == digest(artifact)
        assert result['runtime_verified'] is False and result['performance_verified'] is False
        check('Missing binary', lambda: run(binaries=[root/'missing.exe']), 'Missing compiled artifact')
        (source/'unchanged.txt').write_bytes(b'dirty\n')
        check('Tracked dirty source', run, 'Final mpv source must be clean')
        git(source, 'checkout', '--', 'unchanged.txt')
        (source/'untracked.txt').write_bytes(b'extra\n')
        check('Untracked source', run, 'Final mpv source must be clean')
        (source/'untracked.txt').unlink()
        for key, text in [('baseline_tree', 'parent'), ('source_tree', 'final')]:
            value = copy.deepcopy(lock)
            value['variants']['main'][key] = '0'*40
            if key == 'source_tree':
                value['variants']['main']['step_trees'][-1] = '0'*40
            check('Wrong complete '+text+' tree', lambda v=value: run(v), 'Unexpected complete network '+text+' tree')
        value = copy.deepcopy(lock)
        value['variants']['main']['step_trees'][0] = '0'*40
        check('Wrong intermediate complete tree', lambda: run(value), 'Unexpected complete intermediate tree')
        value = copy.deepcopy(lock)
        value['variants']['main']['source_tree'] = 'TBD'
        check('Placeholder tree', lambda: run(value), 'Invalid complete tree identity')
        value = copy.deepcopy(lock)
        value['variants']['main']['step_trees'] = []
        check('Missing intermediate identities', lambda: run(value), 'Invalid intermediate tree identities')
        for key, message in [('before_source_sha256', 'Baseline source mismatch'), ('source_sha256', 'Final source mismatch')]:
            value = copy.deepcopy(lock)
            value['variants']['main'][key][gate.SOURCE_FILES[0]] = '0'*64
            check('Wrong '+key, lambda v=value: run(v), message)
        value = copy.deepcopy(lock)
        del value['variants']['main']['source_sha256'][gate.SOURCE_FILES[0]]
        check('Incomplete source hashes', lambda: run(value), 'Incomplete source digest set')
        value = copy.deepcopy(lock)
        value['patches'][0]['sha256'] = '0'*64
        check('Wrong patch digest', lambda: run(value), 'Input digest mismatch')
        value = copy.deepcopy(lock)
        value['patches'].reverse()
        check('Reordered patch layers', lambda: run(value), 'Network patch scope differs')
        value = copy.deepcopy(lock)
        value['patches'].pop()
        check('Missing patch layer', lambda: run(value), 'Both ordered network patches')
        value = copy.deepcopy(lock)
        value['patches'][0]['changed_files'].append('unchanged.txt')
        check('Expanded scope', lambda: run(value), 'Network patch scope differs')
        value = copy.deepcopy(lock)
        value['tools_sha256'][first_tool] = '0'*64
        check('Changed gate input', lambda: run(value), 'Input digest mismatch')
        value = copy.deepcopy(lock)
        value['tools_sha256'] = {}
        check('Missing tools', lambda: run(value), 'Exact complete network tool identities are required')
        value = copy.deepcopy(lock)
        del value['tools_sha256'][first_tool]
        check('One omitted tool identity', lambda: run(value), 'Exact complete network tool identities are required')
        value = copy.deepcopy(lock)
        del value['variants']['atmos']
        check('Missing variant', lambda: run(value), 'Both exact variant identities are required')
        first = config/patches[0]['path']
        original = first.read_bytes()
        first.write_bytes(original.replace(b' = 2;', b' = 3;'))
        value = copy.deepcopy(lock)
        value['patches'][0]['sha256'] = digest(first)
        check('Valid scope with altered contents', lambda: run(value), 'Intermediate tree differs from exact packaged patch replay')
        first.write_bytes(original)
        (source/'unchanged.txt').write_bytes(b'unrelated commit\n')
        git(source, 'add', '.')
        git(source, 'commit', '--amend', '--no-edit', '-q')
        value = copy.deepcopy(lock)
        altered = git(source, 'rev-parse', 'HEAD^{tree}')
        value['variants']['main']['source_tree'] = altered
        value['variants']['main']['step_trees'][-1] = altered
        check('Unrelated committed change despite adjusted final hash', lambda: run(value), 'Unexpected incremental source scope')
        git(source, 'reset', '--hard', final)
        target = source/'unchanged.txt'
        target.chmod(target.stat().st_mode | 0o111)
        git(source, 'update-index', '--chmod=+x', 'unchanged.txt')
        git(source, 'commit', '--amend', '--no-edit', '-q')
        check('Unrelated mode change', run, 'Unexpected complete network final tree')
        git(source, 'reset', '--hard', final)
        (a.output/'positive.json').write_text(json.dumps(positive, indent=2)+'\n', encoding='utf-8')
    report = dict(status='NETWORK_SOURCE_GATE_REFUSAL_CONTRACT_PASS', checks=len(checks),
        failures=0, results=checks, tool_sha256=digest(TOOL), runtime_verified=False)
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], checks=len(checks))))


if __name__ == '__main__':
    main()
