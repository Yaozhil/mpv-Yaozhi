"""Exercise actual Git replay and refusal boundaries of the round-two gate."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
TOOL = Path(__file__).resolve().parent / 'verify-round2-source.py'
spec = importlib.util.spec_from_file_location('round2_gate', TOOL)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def git(source, *args):
    result = subprocess.run(['git', '-C', str(source), '-c', 'core.autocrlf=false',
        '-c', 'user.name=Round-two gate test', '-c', 'user.email=round2-test@localhost', *args],
        check=True, capture_output=True, timeout=60)
    return result.stdout.decode().strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []
    with tempfile.TemporaryDirectory(prefix='round2-gate-refusals-') as folder:
        root = Path(folder)
        config = root / 'config'
        source = root / 'source'
        config.mkdir()
        source.mkdir()
        git(source, 'init', '--initial-branch=test')
        for index, relative in enumerate(gate.SOURCE_FILES):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('int old_' + str(index) + ' = 1;\n', encoding='utf-8')
        (source / 'unchanged.txt').write_bytes(b'unchanged\n')
        git(source, 'add', '.')
        git(source, 'commit', '-m', 'Exact old layer')
        baseline_tree = git(source, 'rev-parse', 'HEAD^{tree}')
        before = {p: digest(source / p) for p in gate.SOURCE_FILES}
        for index, relative in enumerate(gate.SOURCE_FILES):
            (source / relative).write_text('int fixed_' + str(index) + ' = 2;\n', encoding='utf-8')
        git(source, 'add', '.')
        git(source, 'commit', '-m', 'Four approved changes')
        final_commit = git(source, 'rev-parse', 'HEAD')
        final_tree = git(source, 'rev-parse', 'HEAD^{tree}')
        patch = config / 'round2.patch'
        patch.write_bytes((git(source, 'format-patch', '-1', '--stdout') + '\n').encode('utf-8'))
        (config / 'tool.txt').write_bytes(b'frozen tool\n')
        expected = {'baseline_tree': baseline_tree, 'source_tree': final_tree,
            'archive_baseline_tree': baseline_tree, 'archive_source_tree': final_tree,
            'before_source_sha256': before,
            'source_sha256': {p: digest(source / p) for p in gate.SOURCE_FILES}}
        lock = {'version': 1,
            'patch': {'path': 'round2.patch', 'sha256': digest(patch), 'changed_files': list(gate.SOURCE_FILES)},
            'variants': {'main': copy.deepcopy(expected), 'atmos': copy.deepcopy(expected)},
            'tools_sha256': {'tool.txt': digest(config / 'tool.txt')}}

        def check(name, operation, failure=None):
            try:
                value = operation()
                if failure is not None:
                    raise AssertionError('Unexpected acceptance: ' + name)
                checks.append({'name': name, 'status': 'PASS'})
                return value
            except (ValueError, subprocess.CalledProcessError) as error:
                if failure is None:
                    raise
                if failure not in str(error):
                    raise AssertionError('Wrong refusal for ' + name + ': ' + str(error)) from error
                checks.append({'name': name, 'status': 'PASS', 'refused': str(error)})

        def run(value=None, **kwargs):
            return gate.verify(source, 'main', value or lock, config=config, **kwargs)

        main_result = check('canonical Git final layer and independent packaged replay', run)
        check('Atmos variant identity', lambda: gate.verify(source, 'atmos', lock, config=config))
        check('explicit archive mode', lambda: run(archive_source=True))
        check('worktree and real index remain untouched', lambda: None if not git(source, 'status', '--porcelain')
              and git(source, 'rev-parse', 'HEAD') == final_commit else (_ for _ in ()).throw(AssertionError('Source mutated')))
        artifact = root / 'mpv.exe'
        artifact.write_bytes(b'test artifact identity only')
        result = check('produced artifact digest bound', lambda: run(binaries=[artifact]))
        assert result['bound_binary_artifacts'][0]['sha256'] == digest(artifact)
        assert result['runtime_verified'] is False and result['performance_verified'] is False
        check('missing produced artifact', lambda: run(binaries=[root / 'missing.exe']), 'Missing compiled artifact')
        (source / 'unchanged.txt').write_bytes(b'dirty\n')
        check('dirty tracked source', run, 'Final mpv source must be clean')
        git(source, 'checkout', '--', 'unchanged.txt')
        (source / 'untracked.txt').write_bytes(b'extra\n')
        check('untracked source', run, 'Final mpv source must be clean')
        (source / 'untracked.txt').unlink()
        changed = copy.deepcopy(lock)
        changed['variants']['main']['baseline_tree'] = '0' * 40
        check('unexpected complete parent tree', lambda: run(changed), 'Unexpected complete round-two parent tree')
        changed = copy.deepcopy(lock)
        changed['variants']['main']['source_tree'] = '0' * 40
        check('unexpected complete final tree', lambda: run(changed), 'Unexpected complete round-two final tree')
        changed = copy.deepcopy(lock)
        changed['variants']['main']['source_tree'] = 'TBD'
        check('placeholder final tree', lambda: run(changed), 'Invalid complete tree identity')
        changed = copy.deepcopy(lock)
        changed['variants']['main']['before_source_sha256'][gate.SOURCE_FILES[0]] = '0' * 64
        check('incorrect per-file baseline identity', lambda: run(changed), 'Baseline source mismatch')
        changed = copy.deepcopy(lock)
        changed['variants']['main']['source_sha256'][gate.SOURCE_FILES[0]] = '0' * 64
        check('incorrect per-file final identity', lambda: run(changed), 'Final source mismatch')
        changed = copy.deepcopy(lock)
        del changed['variants']['main']['source_sha256'][gate.SOURCE_FILES[0]]
        check('incomplete per-file identity', lambda: run(changed), 'Incomplete source digest set')
        changed = copy.deepcopy(lock)
        changed['patch']['sha256'] = '0' * 64
        check('wrong packaged patch digest', lambda: run(changed), 'Input digest mismatch')
        changed = copy.deepcopy(lock)
        changed['patch']['changed_files'].append('unchanged.txt')
        check('expanded approved source scope', lambda: run(changed), 'Round-two scope must be exactly')
        changed = copy.deepcopy(lock)
        changed['tools_sha256']['tool.txt'] = '0' * 64
        check('modified gate input', lambda: run(changed), 'Input digest mismatch')
        changed = copy.deepcopy(lock)
        changed['tools_sha256'] = {}
        check('missing gate identities', lambda: run(changed), 'Round-two tool identities are required')
        original_patch = patch.read_bytes()
        patch.write_bytes(original_patch.replace(b'int fixed_0 = 2;', b'int fixed_0 = 3;'))
        changed = copy.deepcopy(lock)
        changed['patch']['sha256'] = digest(patch)
        check('valid-scope patch with different resulting content', lambda: run(changed), 'Final tree differs from exact packaged patch replay')
        patch.write_bytes(original_patch)
        (source / 'unchanged.txt').write_bytes(b'unrelated committed change\n')
        git(source, 'add', '.')
        git(source, 'commit', '--amend', '--no-edit')
        changed = copy.deepcopy(lock)
        changed['variants']['main']['source_tree'] = git(source, 'rev-parse', 'HEAD^{tree}')
        check('committed unrelated change despite adjusted final tree', lambda: run(changed), 'Unexpected incremental source scope')
        git(source, 'reset', '--hard', final_commit)
        # File modes are part of the complete source tree on canonical CI.
        (source / 'unchanged.txt').chmod((source / 'unchanged.txt').stat().st_mode | 0o111)
        git(source, 'update-index', '--chmod=+x', 'unchanged.txt')
        git(source, 'commit', '--amend', '--no-edit')
        check('unrelated committed Git mode change', run, 'Unexpected complete round-two final tree')
        git(source, 'reset', '--hard', final_commit)
        write_json(args.output / 'positive.json', main_result)
    result = {'status': 'ROUND2_SOURCE_GATE_REFUSAL_CONTRACT_PASS',
        'checks': len(checks), 'failures': 0, 'results': checks,
        'tool_sha256': digest(TOOL), 'runtime_verified': False}
    write_json(args.output / 'report.json', result)
    print(json.dumps({'status': result['status'], 'checks': len(checks)}))


if __name__ == '__main__':
    main()
