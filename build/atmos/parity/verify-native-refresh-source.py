"""Bind the appended native-refresh source layer without changing old gates."""
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
BASELINE_CONFIG = 'fe31dc21d2b249eea3890bad2066dc578d922d0b'
BASELINE_CONFIG_TREE = 'afb4f3015e3dcc057426a51e80a8757d5d42a5e8'
BASELINE_LOCK = 'a1721340c1819bad1e8d10aa070c5224aa72b73d8283b346fb7186e4f0c5f4fd'
BASELINE_DEPENDENCY_LOCK = '515e948e1235a2a73216d59521ad449ad6357b4a543aaabb4b2886aeb28c3a55'
SOURCE_FILES = ('video/out/secondary_ass_fresh_video.h', 'video/out/vo.c')
REQUIRED_TOOLS = frozenset((
    '.github/workflows/build-mpv-v100-parity.yml',
    'build/atmos/parity/prepare-native-refresh-winbuild.py',
    'build/atmos/parity/verify-native-refresh-source.py',
    'build/atmos/parity/test-native-refresh-source-gate.py',
    'build/atmos/parity/verify-native-refresh-contract.py',
    'build/feedback/tests/verify-secondary-ass-fresh-video.c',
    'build/feedback/tests/verify-danmaku-native-recovery.lua',
    'build/feedback/tests/fixtures/native-refresh-render.lua',
    'build/feedback/tests/fixtures/modules/blackbar.lua',
))


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(argv, env=None):
    result = subprocess.run([str(p) for p in argv], capture_output=True, env=env,
        timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0, 'Command failed: '+repr(argv)+'\n'+
            result.stderr.decode('utf-8', 'replace')[:4000])
    return result.stdout


def git(source, *args, index=None):
    env = os.environ.copy()
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    return command(['git', '-C', source, '-c', 'core.autocrlf=false', *args], env)


def checked_file(config, relative, expected):
    require(isinstance(relative, str) and relative and '\\' not in relative and
        not Path(relative).is_absolute() and '..' not in Path(relative).parts,
        'Unsafe configuration path')
    path = (config/relative).resolve()
    require(path.is_relative_to(config.resolve()), 'Configuration path escape')
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected),
            'Invalid digest: '+relative)
    require(path.is_file() and sha(path.read_bytes()) == expected, 'Input digest mismatch: '+relative)
    return path


def validate_lock(lock, config=CONFIG):
    require(lock['version'] == 1, 'Review a new native-refresh schema')
    require(lock['parent_config_commit'] == BASELINE_CONFIG and
        lock['parent_config_tree'] == BASELINE_CONFIG_TREE and
        lock['parent_source_lock_sha256'] == BASELINE_LOCK and
        lock['dependency_lock_sha256'] == BASELINE_DEPENDENCY_LOCK,
        'Frozen parent/dependency identity differs')
    checked_file(config, 'build/atmos/parity/source-lock.json', BASELINE_LOCK)
    checked_file(config, 'build/atmos/parity/dependency-lock.json', BASELINE_DEPENDENCY_LOCK)
    item = lock['patch']
    require(tuple(item['changed_files']) == SOURCE_FILES, 'Unexpected approved source scope')
    patch = checked_file(config, item['path'], item['sha256'])
    rows = git(config, 'apply', '--numstat', '-z', str(patch)).split(b'\0')
    paths = []
    for row in rows:
        if not row:
            continue
        parts = row.split(b'\t', 2)
        require(len(parts) == 3 and parts[2] and parts[0].isdigit() and parts[1].isdigit(),
                'Malformed or binary patch path')
        paths.append(parts[2].decode('utf-8'))
    require(tuple(sorted(paths)) == SOURCE_FILES, 'Actual patch source scope differs')
    require(set(lock['variants']) == {'main', 'atmos'}, 'Both exact variant identities are required')
    for variant, expected in lock['variants'].items():
        for name in ('baseline_tree', 'source_tree'):
            require(isinstance(expected[name], str) and re.fullmatch('[0-9a-f]{40}', expected[name]),
                    'Invalid complete source tree: '+variant+'/'+name)
        for name in ('before_source_sha256', 'source_sha256'):
            require(set(expected[name]) == set(SOURCE_FILES), 'Incomplete source digest set')
            require(all((v is None and name == 'before_source_sha256' and
                         k == 'video/out/secondary_ass_fresh_video.h') or
                        (isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v))
                        for k,v in expected[name].items()), 'Invalid source digest')
        require(expected['before_source_sha256']['video/out/secondary_ass_fresh_video.h'] is None,
                'New helper must not replace an existing parent file')
    require(set(lock['tools_sha256']) == REQUIRED_TOOLS, 'Exact complete new tool identities are required')
    for relative, expected in lock['tools_sha256'].items():
        checked_file(config, relative, expected)
    return patch


def validate_parent_config(parent):
    parent = parent.resolve()
    require(git(parent, 'rev-parse', 'HEAD').decode().strip() == BASELINE_CONFIG,
            'Wrong legacy speaker configuration commit')
    require(git(parent, 'rev-parse', 'HEAD^{tree}').decode().strip() == BASELINE_CONFIG_TREE,
            'Wrong legacy speaker configuration tree')
    require(not git(parent, 'status', '--porcelain', '--untracked-files=all').strip(),
            'Legacy speaker configuration must be completely clean')
    checked_file(parent, 'build/atmos/parity/source-lock.json', BASELINE_LOCK)
    checked_file(parent, 'build/atmos/parity/dependency-lock.json', BASELINE_DEPENDENCY_LOCK)
    return parent


def verify(source, variant, lock, *, config=CONFIG, binaries=(), parent_config=None,
           compiled=False):
    source, config = source.resolve(), config.resolve()
    patch = validate_lock(lock, config)
    require(not git(source, 'status', '--porcelain', '--untracked-files=all').strip(),
            'Final mpv source must be completely clean')
    final = git(source, 'rev-parse', 'HEAD').decode().strip()
    parent = git(source, 'rev-parse', 'HEAD^').decode().strip()
    final_tree = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    parent_tree = git(source, 'rev-parse', 'HEAD^^{tree}').decode().strip()
    expected = lock['variants'][variant]
    require(parent_tree == expected['baseline_tree'], 'Unexpected complete native-refresh parent tree')
    require(final_tree == expected['source_tree'], 'Unexpected complete native-refresh final tree')
    require(tuple(sorted(git(source, 'diff', '--name-only', parent, final).decode().splitlines()))
            == SOURCE_FILES, 'Unexpected appended source scope')
    for relative in SOURCE_FILES:
        before = expected['before_source_sha256'][relative]
        if before is None:
            require(not git(source, 'ls-tree', parent, '--', relative).strip(),
                    'Expected new helper absent from parent: '+relative)
        else:
            require(sha(git(source, 'show', parent+':'+relative)) == before,
                    'Baseline source mismatch: '+relative)
        require(sha((source/relative).read_bytes()) == expected['source_sha256'][relative],
                'Final source mismatch: '+relative)
    with tempfile.TemporaryDirectory(prefix='native-refresh-index-') as folder:
        index = Path(folder)/'index'
        git(source, 'read-tree', parent, index=index)
        git(source, 'apply', '--cached', '--check', str(patch), index=index)
        git(source, 'apply', '--cached', str(patch), index=index)
        replay = git(source, 'write-tree', index=index).decode().strip()
        require(replay == final_tree, 'Final tree differs from packaged patch replay')
    parent_report = None
    if parent_config is not None:
        old_config = validate_parent_config(parent_config)
        # A separate shared local clone preserves the exact compiled checkout,
        # its HEAD, real index and all worktree bytes throughout parent checks.
        with tempfile.TemporaryDirectory(prefix='native-refresh-parent-') as folder:
            old_source, output = Path(folder)/'source', Path(folder)/'network.json'
            network_config = Path(folder)/'network-config'
            # The speaker verifier intentionally preserves df1084's original
            # network workflow identity. Let that exact fe31 tool create its
            # own checked df1084 view instead of evaluating a historic network
            # lock against the newer speaker workflow.
            command([sys.executable, '-B', old_config/'build/atmos/parity/verify-speakers-source.py',
                '--prepare-legacy-config', network_config])
            command(['git', 'clone', '--quiet', '--shared', '--no-checkout', source, old_source])
            git(old_source, 'checkout', '--detach', parent)
            command([sys.executable, '-B', network_config/'build/atmos/parity/verify-network-source.py',
                '--source', old_source, '--variant', variant, '--output', output])
            parent_report = json.loads(output.read_bytes())
            require(parent_report['status'] == 'EXACT_NETWORK_FINAL_SOURCE_AND_PATCH_REPLAY_PASS' and
                parent_report['source_tree'] == parent_tree, 'Frozen network parent gate failed')
    require(not compiled or parent_config is not None, 'Compiled gate requires frozen parent verification')
    require(not compiled or len(binaries) == 2, 'Compiled gate requires exactly mpv.exe and mpv.com')
    items = []
    for binary in binaries:
        binary = binary.resolve()
        require(binary.is_file() and binary.stat().st_size > 0, 'Missing compiled artifact')
        items.append(dict(path=str(binary), sha256=sha(binary.read_bytes()), size=binary.stat().st_size))
    require(len({p['path'] for p in items}) == len(items), 'Duplicate compiled artifact')
    if compiled:
        require({Path(p['path']).name for p in items} == {'mpv.exe', 'mpv.com'},
                'Compiled gate requires exactly mpv.exe and mpv.com')
    require(git(source, 'rev-parse', 'HEAD').decode().strip() == final and
        not git(source, 'status', '--porcelain', '--untracked-files=all').strip(),
        'Actual final source changed during verification')
    return dict(status='EXACT_NATIVE_REFRESH_FINAL_SOURCE_AND_PATCH_REPLAY_PASS',
        variant=variant, source_commit=final, source_tree=final_tree, baseline_commit=parent,
        baseline_tree=parent_tree, patch_replay_tree=replay, packaged_patch_sha256=lock['patch']['sha256'],
        changed_files=list(SOURCE_FILES), source_sha256=expected['source_sha256'],
        all_other_tracked_source_unchanged=True, actual_final_checkout_unchanged=True,
        frozen_network_parent_report=parent_report, bound_binary_artifacts=items,
        runtime_verified=False, performance_verified=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--variant', required=True, choices=('main', 'atmos'))
    p.add_argument('--parent-config', required=True, type=Path)
    p.add_argument('--compiled', action='store_true')
    p.add_argument('--binary', type=Path, action='append', default=[])
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    result = dict(status='NATIVE_REFRESH_SOURCE_FAILED', runtime_verified=False)
    try:
        lock = json.loads((HERE/'native-refresh-lock.json').read_bytes())
        result = verify(a.source, a.variant, lock, parent_config=a.parent_config,
                        compiled=a.compiled, binaries=a.binary)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
