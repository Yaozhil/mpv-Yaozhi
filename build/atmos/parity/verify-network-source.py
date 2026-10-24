"""Verify both exact incremental Windows/HTTP trees and bind produced binaries.

The returned baseline is the actual round-two commit. Historical source gates
run on that unchanged layer; this gate checks the final two-commit layer by
independent index-only replay, including each intermediate complete tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]
PATCH_SCOPES = (
    ('misc/path_utils.c', 'options/parse_commandline.c', 'osdep/io.c', 'test/paths.c'),
    ('stream/stream_curl.c',),
)
SOURCE_FILES = tuple(sorted(p for group in PATCH_SCOPES for p in group))
REQUIRED_TOOLS = frozenset((
    'build/atmos/parity/prepare-network-winbuild.py',
    'build/atmos/parity/verify-network-source.py',
    'build/atmos/parity/test-network-source-gate.py',
    'build/atmos/parity/dependency-lock.json',
    'build/atmos/parity/prepare-dependency-lock.py',
    'build/atmos/parity/verify-dependency-build.py',
    'build/atmos/parity/test-dependency-build-gate.py',
    'build/atmos/parity/tests/http-range-runtime.py',
    'build/atmos/parity/tests/http-playback-runtime.py',
    'build/atmos/parity/tests/windows-paths-runtime.py',
    'build/atmos/parity/tests/windows-paths-runtime.lua',
    '.github/workflows/build-mpv-v100-parity.yml',
))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(source, *args, index=None):
    env = os.environ.copy()
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    return subprocess.check_output(['git', '-C', str(source), '-c',
        'core.autocrlf=false', *args], env=env, timeout=90)


def checked_file(config, relative, expected):
    path = (config/relative).resolve()
    require(path.is_relative_to(config), 'Input path escapes configuration: '+relative)
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None, 'Invalid input digest: '+relative)
    require(sha(path.read_bytes()) == expected, 'Input digest mismatch: '+relative)
    return path


def validate_lock(lock, config=CONFIG):
    require(lock['version'] == 1, 'Review a new network schema version')
    require(len(lock['patches']) == len(PATCH_SCOPES), 'Both ordered network patches are required')
    patches = []
    for item, scope in zip(lock['patches'], PATCH_SCOPES):
        require(sorted(item['changed_files']) == list(scope), 'Network patch scope differs from approved files')
        patch = checked_file(config, item['path'], item['sha256'])
        records = git(config, 'apply', '--numstat', '-z', str(patch)).split(b'\0')
        paths = []
        for record in records:
            if not record:
                continue
            fields = record.split(b'\t', 2)
            require(len(fields) == 3 and fields[2], 'Renamed or malformed patch path is not allowed')
            path = fields[2].decode('utf-8')
            require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe patch path: '+path)
            paths.append(path)
        require(sorted(paths) == list(scope), 'Packaged patch scope differs from approved files')
        patches.append(patch)
    require(set(lock['variants']) == {'main', 'atmos'}, 'Both exact variant identities are required')
    for variant, expected in lock['variants'].items():
        for prefix in ('', 'archive_'):
            for key in ('baseline_tree', 'source_tree'):
                require(re.fullmatch('[0-9a-f]{40}', expected[prefix+key]) is not None,
                    'Invalid complete tree identity: '+variant+'/'+prefix+key)
            trees = expected[prefix+'step_trees']
            require(len(trees) == len(patches) and all(re.fullmatch('[0-9a-f]{40}', t) for t in trees),
                    'Invalid intermediate tree identities: '+variant)
            require(trees[-1] == expected[prefix+'source_tree'], 'Last step must be the final tree')
        for key in ('before_source_sha256', 'source_sha256'):
            require(set(expected[key]) == set(SOURCE_FILES), 'Incomplete source digest set: '+variant+'/'+key)
            require(all(re.fullmatch('[0-9a-f]{64}', v) for v in expected[key].values()),
                    'Invalid source digest: '+variant+'/'+key)
    require(set(lock['tools_sha256']) == REQUIRED_TOOLS, 'Exact complete network tool identities are required')
    for path, expected in lock['tools_sha256'].items():
        checked_file(config, path, expected)
    return patches


def verify(source, variant, lock, archive_source=False, binaries=(), config=CONFIG):
    source, config = source.resolve(), config.resolve()
    patches = validate_lock(lock, config)
    require(not git(source, 'status', '--porcelain').strip(), 'Final mpv source must be clean')
    final = git(source, 'rev-parse', 'HEAD').decode().strip()
    baseline = git(source, 'rev-parse', 'HEAD~2').decode().strip()
    final_tree = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    baseline_tree = git(source, 'rev-parse', baseline+'^{tree}').decode().strip()
    expected = lock['variants'][variant]
    prefix = 'archive_' if archive_source else ''
    require(baseline_tree == expected[prefix+'baseline_tree'], 'Unexpected complete network parent tree')
    require(final_tree == expected[prefix+'source_tree'], 'Unexpected complete network final tree')
    changed = sorted(git(source, 'diff', '--name-only', baseline, final).decode().splitlines())
    require(changed == list(SOURCE_FILES), 'Unexpected incremental source scope: '+repr(changed))
    for path in SOURCE_FILES:
        require(sha(git(source, 'show', baseline+':'+path)) == expected['before_source_sha256'][path],
                'Baseline source mismatch: '+path)
        require(sha((source/path).read_bytes()) == expected['source_sha256'][path], 'Final source mismatch: '+path)
    observed_steps = []
    for number, scope in enumerate(PATCH_SCOPES):
        commit = git(source, 'rev-parse', 'HEAD~'+str(len(patches)-1-number)).decode().strip()
        require(sorted(git(source, 'diff', '--name-only', commit+'^', commit).decode().splitlines()) == list(scope),
                'Unexpected per-step source scope')
        tree = git(source, 'rev-parse', commit+'^{tree}').decode().strip()
        require(tree == expected[prefix+'step_trees'][number], 'Unexpected complete intermediate tree')
        observed_steps.append(tree)
    with tempfile.TemporaryDirectory(prefix='network-source-index-') as folder:
        index = Path(folder)/'index'
        git(source, 'read-tree', baseline, index=index)
        for patch, tree in zip(patches, observed_steps):
            git(source, 'apply', '--cached', '--check', str(patch), index=index)
            git(source, 'apply', '--cached', str(patch), index=index)
            replay = git(source, 'write-tree', index=index).decode().strip()
            require(replay == tree, 'Intermediate tree differs from exact packaged patch replay')
    binary_items = []
    for binary in binaries:
        path = binary.resolve()
        require(path.is_file() and path.stat().st_size > 0, 'Missing compiled artifact: '+str(path))
        binary_items.append(dict(path=str(path), sha256=sha(path.read_bytes()), size=path.stat().st_size))
    return dict(status='EXACT_NETWORK_FINAL_SOURCE_AND_PATCH_REPLAY_PASS', variant=variant,
        source_commit=final, source_tree=final_tree, baseline_commit=baseline, baseline_tree=baseline_tree,
        step_trees=observed_steps, patch_replay_tree=replay,
        packaged_patch_sha256=[item['sha256'] for item in lock['patches']],
        changed_files=list(SOURCE_FILES), source_sha256=expected['source_sha256'],
        all_other_tracked_source_unchanged=True,
        source_mode='windows-archive' if archive_source else 'canonical-git-checkout',
        bound_binary_artifacts=binary_items, runtime_verified=False, performance_verified=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--variant', required=True, choices=['main', 'atmos'])
    p.add_argument('--archive-source', action='store_true')
    p.add_argument('--binary', action='append', default=[], type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    result = dict(status='NETWORK_SOURCE_FAILED', runtime_verified=False)
    try:
        lock = json.loads((HERE/'source-lock.json').read_bytes())['network_stability']
        result = verify(a.source, a.variant, lock, a.archive_source, a.binary)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
