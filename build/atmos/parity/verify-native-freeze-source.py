"""Bind an appended ASS recovery layer to the exact installed 1393 parent."""
import argparse
import hashlib
import importlib.util
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
PARENT_CONFIG = '1393dd3715ab02e87162dd541886fabb0766fb6c'
PARENT_CONFIG_TREE = '58fa116ff1e9c96268e09dae6b561a8ff1f54c84'
PARENT_NATIVE_LOCK_SHA256 = 'b1b52ee787344124e52c47712c06ae2ecada1e42e1781d4d9b54fb24adfb27c4'
PARENT_SOURCE_LOCK_SHA256 = 'a1721340c1819bad1e8d10aa070c5224aa72b73d8283b346fb7186e4f0c5f4fd'
DEPENDENCY_LOCK_SHA256 = '515e948e1235a2a73216d59521ad449ad6357b4a543aaabb4b2886aeb28c3a55'
PARENT_TREES = {
    'main': '61a2676338e340c0b94e2c9ea92964edd9194b5c',
    'atmos': 'e0e82e9b934e5a356955053755914acea7e858ab',
}
ALLOWED_SOURCE_FILES = frozenset((
    'video/out/vo.c',
    'video/out/secondary_ass_physical.h',
))
REQUIRED_TOOLS = frozenset((
    '.github/workflows/build-mpv-v100-parity.yml',
    'build/atmos/parity/prepare-native-freeze-winbuild.py',
    'build/atmos/parity/verify-native-freeze-source.py',
    'build/atmos/parity/verify-native-freeze-contract.py',
    'build/atmos/parity/test-native-freeze-source-gate.py',
    'build/atmos/parity/freeze-native-freeze-layer.py',
))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(argv, env=None):
    result = subprocess.run([str(p) for p in argv], capture_output=True,
        env=env, timeout=120,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0, 'Command failed: '+repr(argv)+'\n'+
        result.stderr.decode('utf-8', 'replace')[-6000:])
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
    require(path.is_file() and sha(path.read_bytes()) == expected,
        'Input digest mismatch: '+relative)
    return path


def changed_paths(config, patch):
    paths = []
    for row in git(config, 'apply', '--numstat', '-z', patch).split(b'\0'):
        if not row:
            continue
        parts = row.split(b'\t', 2)
        require(len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit(),
            'Malformed, rename or binary source patch')
        paths.append(parts[2].decode('utf-8'))
    require(len(paths) == len(set(paths)), 'Duplicate source patch path')
    return sorted(paths)


def validate_lock(lock, config=CONFIG):
    require(lock['version'] == 1, 'Review a new native-freeze schema')
    require(lock['parent_config_commit'] == PARENT_CONFIG and
        lock['parent_config_tree'] == PARENT_CONFIG_TREE and
        lock['parent_native_refresh_lock_sha256'] == PARENT_NATIVE_LOCK_SHA256 and
        lock['parent_source_lock_sha256'] == PARENT_SOURCE_LOCK_SHA256 and
        lock['dependency_lock_sha256'] == DEPENDENCY_LOCK_SHA256,
        'Frozen installed parent/dependency identity differs')
    for rel, expected in (
        ('build/atmos/parity/source-lock.json', PARENT_SOURCE_LOCK_SHA256),
        ('build/atmos/parity/dependency-lock.json', DEPENDENCY_LOCK_SHA256),
        ('build/atmos/parity/native-refresh-lock.json', PARENT_NATIVE_LOCK_SHA256)):
        checked_file(config, rel, expected)
    old = json.loads((config/'build/atmos/parity/native-refresh-lock.json').read_bytes())
    checked_file(config, old['patch']['path'], old['patch']['sha256'])
    # The current workflow appends this layer. Execute the original workflow
    # identity only from the exact parent view; preserve every other old input.
    for rel, expected in old['tools_sha256'].items():
        if rel != '.github/workflows/build-mpv-v100-parity.yml':
            checked_file(config, rel, expected)
    item = lock['patch']
    files = item['changed_files']
    require(files == sorted(set(files)) and 'video/out/vo.c' in files and
        set(files) <= ALLOWED_SOURCE_FILES, 'Unexpected approved source scope')
    patch = checked_file(config, item['path'], item['sha256'])
    require(changed_paths(config, patch) == files, 'Actual patch scope differs')
    require(set(lock['variants']) == set(PARENT_TREES), 'Both exact variants required')
    for variant, expected in lock['variants'].items():
        require(expected['baseline_tree'] == PARENT_TREES[variant],
            'Wrong installed complete parent tree: '+variant)
        require(isinstance(expected['source_tree'], str) and
            re.fullmatch('[0-9a-f]{40}', expected['source_tree']),
            'Unfrozen complete source tree: '+variant)
        for field in ('before_source_sha256', 'source_sha256'):
            values = expected[field]
            require(set(values) == set(files), 'Incomplete source digest set')
            require(all((v is None and field == 'before_source_sha256') or
                isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v)
                for v in values.values()), 'Invalid source digest')
    require(set(lock['tools_sha256']) >= REQUIRED_TOOLS,
        'Incomplete new source gate/tool identities')
    for relative, expected in lock['tools_sha256'].items():
        checked_file(config, relative, expected)
    require(lock['cpu_contracts'], 'A reviewed actual-source CPU contract is required')
    for contract in lock['cpu_contracts']:
        require(contract['runner'] in lock['tools_sha256'], 'Unbound CPU runner')
        require(contract['kind'] in ('c', 'extracted-epoch'), 'Unknown CPU runner kind')
        require(isinstance(contract['expected_stdout_prefix'], str) and
            contract['expected_stdout_prefix'], 'Missing CPU success marker')
        require(all(isinstance(arg, str) for arg in contract.get('run_arguments', [])),
            'Invalid CPU run arguments')
        for rel in contract.get('inputs', []):
            require(rel in lock['tools_sha256'], 'Unbound CPU fixture input')
    return patch


def validate_parent_config(parent):
    parent = parent.resolve()
    require(git(parent, 'rev-parse', 'HEAD').decode().strip() == PARENT_CONFIG,
        'Wrong installed parent configuration commit')
    require(git(parent, 'rev-parse', 'HEAD^{tree}').decode().strip() == PARENT_CONFIG_TREE,
        'Wrong installed parent configuration tree')
    require(not git(parent, 'status', '--porcelain', '--untracked-files=all').strip(),
        'Installed parent configuration must be completely clean')
    checked_file(parent, 'build/atmos/parity/native-refresh-lock.json', PARENT_NATIVE_LOCK_SHA256)
    return parent


def prepare_parent_config(destination):
    require(not destination.exists(), 'Parent configuration destination exists')
    git(CONFIG, 'worktree', 'add', '--detach', destination, PARENT_CONFIG)
    validate_parent_config(destination)
    return dict(status='EXACT_INSTALLED_PARENT_CONFIG_MATERIALIZED',
        parent_config_commit=PARENT_CONFIG, parent_config_tree=PARENT_CONFIG_TREE)


def verify(source, variant, lock, *, parent_config, legacy_speaker_config,
           config=CONFIG, binaries=(), compiled=False):
    source, config = source.resolve(), config.resolve()
    patch = validate_lock(lock, config)
    parent_config = validate_parent_config(parent_config)
    require(not git(source, 'status', '--porcelain', '--untracked-files=all').strip(),
        'Final mpv source must be completely clean')
    final = git(source, 'rev-parse', 'HEAD').decode().strip()
    parent = git(source, 'rev-parse', 'HEAD^').decode().strip()
    final_tree = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    parent_tree = git(source, 'rev-parse', 'HEAD^^{tree}').decode().strip()
    expected = lock['variants'][variant]
    files = lock['patch']['changed_files']
    require(parent_tree == expected['baseline_tree'], 'Unexpected installed parent source tree')
    require(final_tree == expected['source_tree'], 'Unexpected complete final source tree')
    require(sorted(git(source, 'diff', '--name-only', parent, final).decode().splitlines()) == files,
        'Unexpected appended source scope')
    for relative in files:
        before = expected['before_source_sha256'][relative]
        if before is None:
            require(not git(source, 'ls-tree', parent, '--', relative).strip(),
                'Expected new source file absent from installed parent')
        else:
            require(sha(git(source, 'show', parent+':'+relative)) == before,
                'Installed parent source digest differs: '+relative)
        require(sha((source/relative).read_bytes()) == expected['source_sha256'][relative],
            'Final source digest differs: '+relative)
    with tempfile.TemporaryDirectory(prefix='native-freeze-replay-') as folder:
        index = Path(folder)/'index'
        git(source, 'read-tree', parent, index=index)
        git(source, 'apply', '--cached', '--check', patch, index=index)
        git(source, 'apply', '--cached', patch, index=index)
        replay = git(source, 'write-tree', index=index).decode().strip()
        require(replay == final_tree, 'Final tree differs from packaged patch replay')
        old_source, output = Path(folder)/'installed-source', Path(folder)/'installed-proof.json'
        command(['git', 'clone', '--quiet', '--shared', '--no-checkout', source, old_source])
        git(old_source, 'checkout', '--detach', parent)
        command([sys.executable, '-B', parent_config/'build/atmos/parity/verify-native-refresh-source.py',
            '--source', old_source, '--variant', variant, '--parent-config', legacy_speaker_config,
            '--output', output])
        parent_report = json.loads(output.read_bytes())
        require(parent_report['status'] == 'EXACT_NATIVE_REFRESH_FINAL_SOURCE_AND_PATCH_REPLAY_PASS' and
            parent_report['source_tree'] == parent_tree,
            'Frozen installed native-refresh source gate failed')
    require(not compiled or len(binaries) == 2,
        'Compiled gate requires exactly mpv.exe and mpv.com')
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
        'Actual final checkout changed during verification')
    return dict(status='EXACT_NATIVE_FREEZE_FINAL_SOURCE_AND_PATCH_REPLAY_PASS',
        variant=variant, source_commit=final, source_tree=final_tree,
        baseline_commit=parent, baseline_tree=parent_tree, patch_replay_tree=replay,
        packaged_patch_sha256=lock['patch']['sha256'], changed_files=files,
        source_sha256=expected['source_sha256'], frozen_installed_parent_report=parent_report,
        all_other_tracked_source_unchanged=True, actual_final_checkout_unchanged=True,
        bound_binary_artifacts=items, runtime_verified=False, performance_verified=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-parent-config', type=Path)
    p.add_argument('--source', type=Path)
    p.add_argument('--variant', choices=tuple(PARENT_TREES))
    p.add_argument('--parent-config', type=Path)
    p.add_argument('--legacy-speaker-config', type=Path)
    p.add_argument('--compiled', action='store_true')
    p.add_argument('--binary', type=Path, action='append', default=[])
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    result = dict(status='NATIVE_FREEZE_SOURCE_FAILED', runtime_verified=False)
    try:
        if a.prepare_parent_config is not None:
            require(not any((a.source, a.variant, a.parent_config, a.compiled, a.binary)),
                'Do not combine parent preparation with source acceptance')
            result = prepare_parent_config(a.prepare_parent_config)
        else:
            require(all((a.source, a.variant, a.parent_config, a.legacy_speaker_config)),
                'Source, variant and both frozen parent configuration views required')
            lock = json.loads((HERE/'native-freeze-lock.json').read_bytes())
            result = verify(a.source, a.variant, lock, parent_config=a.parent_config,
                legacy_speaker_config=a.legacy_speaker_config, compiled=a.compiled, binaries=a.binary)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
