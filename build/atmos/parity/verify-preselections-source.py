"""Bind AV3A content selection to exact mpv and dependency source identities.

The mpv gate runs at the new final HEAD, then returns its parent so historical
round-one and HOLD/EOF/PTS gates can retain their original checkout boundary.
Dependency verification replays the locked old and new patch chain in temporary
Git indexes and compares the complete observed source tree without touching the
build checkout's source files or index. Runtime listening is a separate gate.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(source, *args, index=None, data=None):
    env = os.environ.copy()
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    return subprocess.check_output(
        ['git', '-C', str(source), '-c', 'core.autocrlf=false', *args],
        input=data, env=env, timeout=90,
    )


def config_file(relative):
    path = (CONFIG / relative).resolve()
    require(path.is_relative_to(CONFIG), f'Path escapes configuration: {relative}')
    return path


def checked_file(item):
    path = config_file(item['path'])
    require(digest(path.read_bytes()) == item['sha256'], f'Input digest mismatch: {item["path"]}')
    return path


def changed_paths(source, patch):
    # --numstat -z provides unambiguous paths and rejects malformed patches.
    records = git(source, 'apply', '--numstat', '-z', str(patch)).split(b'\0')
    paths = []
    for record in records:
        if not record:
            continue
        parts = record.split(b'\t', 2)
        require(len(parts) == 3 and parts[2], 'Renamed or malformed patch path is not allowed')
        path = parts[2].decode('utf-8')
        require(not Path(path).is_absolute() and '..' not in Path(path).parts,
                f'Unsafe patch path: {path}')
        paths.append(path)
    return sorted(paths)


def validate_lock(lock):
    require(lock['version'] == 1, 'Review a new lock schema version')
    require(set(lock['patches']) == {'mpv', 'sdk', 'ffmpeg'}, 'Exactly three separately reversible patches are required')
    for kind, layer in lock['patches'].items():
        path = checked_file(layer)
        require(layer['changed_files'] and len(set(layer['changed_files'])) == len(layer['changed_files']),
                f'Empty or duplicate patch scope: {kind}')
        require(changed_paths(CONFIG, path) == sorted(layer['changed_files']), f'Patch scope mismatch: {kind}')
    for path, expected in lock['tools_sha256'].items():
        require(digest(config_file(path).read_bytes()) == expected, f'Tool digest mismatch: {path}')


def check_hashes(source, before_ref, expected, allowed):
    require(set(expected['before_source_sha256']) == set(allowed), 'Incomplete before-source digest set')
    require(set(expected['source_sha256']) == set(allowed), 'Incomplete final-source digest set')
    for path in allowed:
        before_digest = expected['before_source_sha256'][path]
        before = git(source, 'show', before_ref + ':' + path) if before_digest is not None else None
        require((digest(before) if before is not None else None) == before_digest,
                f'Baseline source mismatch: {path}')
        after_digest = expected['source_sha256'][path]
        after = (source / path).read_bytes() if after_digest is not None else None
        require((digest(after) if after is not None else None) == after_digest,
                f'Final source mismatch: {path}')
        if after_digest is None:
            require(not (source / path).exists(), f'Deleted source still exists: {path}')


def verify_mpv(source, variant, lock, archive=False):
    source = source.resolve()
    require(not git(source, 'status', '--porcelain').strip(), 'mpv source must be clean')
    final = git(source, 'rev-parse', 'HEAD').decode().strip()
    baseline = git(source, 'rev-parse', 'HEAD^').decode().strip()
    observed_tree = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    baseline_tree = git(source, 'rev-parse', 'HEAD^^{tree}').decode().strip()
    expected = lock['variants'][variant]
    prefix = 'archive_' if archive else ''
    require(baseline_tree == expected[prefix + 'baseline_tree'], 'Unexpected complete preselection parent tree')
    require(observed_tree == expected[prefix + 'source_tree'], 'Unexpected complete preselection final tree')
    allowed = sorted(lock['patches']['mpv']['changed_files'])
    changed = sorted(git(source, 'diff', '--name-only', baseline, final).decode().splitlines())
    require(changed == allowed, f'Unexpected mpv incremental scope: {changed}')
    check_hashes(source, baseline, expected, allowed)
    return {
        'status': 'EXACT_PRESELECTIONS_MPV_SOURCE_PASS', 'variant': variant,
        'source_commit': final, 'source_tree': observed_tree,
        'baseline_commit': baseline, 'baseline_tree': baseline_tree,
        'changed_files': allowed, 'all_other_tracked_source_unchanged': True,
        'source_mode': 'windows-archive' if archive else 'canonical-git-checkout',
        'compiled': False, 'runtime_verified': False, 'performance_verified': False,
    }


@contextmanager
def temporary_index(source):
    with tempfile.TemporaryDirectory(prefix='avs3a-preselection-index-') as folder:
        path = Path(folder) / 'index'
        git(source, 'read-tree', 'HEAD', index=path)
        yield path


def index_entry(source, index, path):
    raw = git(source, 'ls-files', '-s', '-z', '--', path, index=index).rstrip(b'\0')
    if not raw:
        return None
    mode, obj, stage_path = raw.split(b' ', 2)
    require(stage_path.startswith(b'0\t'), f'Unmerged source path: {path}')
    return mode.decode(), obj.decode()


def install_blob(source, index, path, content, mode=None):
    entry = index_entry(source, index, path)
    mode = mode or (entry[0] if entry else '100644')
    obj = git(source, 'hash-object', '-w', '--stdin', data=content).decode().strip()
    git(source, 'update-index', '--add', '--cacheinfo', f'{mode},{obj},{path}', index=index)


def replay_patch(source, index, item):
    path = checked_file(item)
    git(source, 'apply', '--cached', '--check', str(path), index=index)
    git(source, 'apply', '--cached', str(path), index=index)


def observe_worktree(source, index):
    # Start from the complete pinned tree. Change only files visible as actual
    # source edits, preserving SDK sparse-checkout entries outside the checkout.
    dirty = git(source, 'diff', '--name-only', '-z', 'HEAD').split(b'\0')
    untracked = git(source, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
    paths = sorted({path.decode('utf-8') for path in dirty + untracked if path})
    for relative in paths:
        path = source / relative
        if not path.exists() and not path.is_symlink():
            git(source, 'update-index', '--force-remove', '--', relative, index=index)
            continue
        mode = '120000' if path.is_symlink() else ('100755' if path.stat().st_mode & stat.S_IXUSR else '100644')
        content = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        install_blob(source, index, relative, content, mode)
    return git(source, 'write-tree', index=index).decode().strip(), paths


def verify_dependency(source, kind, lock):
    source = source.resolve()
    expected = lock['dependencies'][kind]
    require(git(source, 'rev-parse', 'HEAD').decode().strip() == expected['base_commit'],
            f'Unexpected pinned {kind} commit')
    with temporary_index(source) as index:
        for relative in expected.get('normalize_lf_files', []):
            entry = index_entry(source, index, relative)
            require(entry is not None, f'Missing normalization input: {relative}')
            content = git(source, 'cat-file', 'blob', entry[1])
            install_blob(source, index, relative, content.replace(b'\r\n', b'\n'))
        for seed in expected.get('seed_files', []):
            seed_path = config_file(seed['source'])
            content = seed_path.read_bytes()
            require(digest(content) == seed['sha256'], f'Seed digest mismatch: {seed["source"]}')
            install_blob(source, index, seed['path'], content, seed.get('mode', '100644'))
        require(expected['baseline_patches'], f'Missing historical {kind} patch chain')
        for patch in expected['baseline_patches']:
            replay_patch(source, index, patch)
        baseline_tree = git(source, 'write-tree', index=index).decode().strip()
        layer = lock['patches'][kind]
        allowed = sorted(layer['changed_files'])
        require(set(expected['before_source_sha256']) == set(allowed), f'Incomplete {kind} before digest set')
        require(set(expected['source_sha256']) == set(allowed), f'Incomplete {kind} after digest set')
        for relative, value in expected['before_source_sha256'].items():
            entry = index_entry(source, index, relative)
            content = git(source, 'cat-file', 'blob', entry[1]) if entry else None
            require((digest(content) if content is not None else None) == value,
                    f'{kind} baseline source mismatch: {relative}')
        replay_patch(source, index, layer)
        final_tree = git(source, 'write-tree', index=index).decode().strip()
        incremental = sorted(git(source, 'diff', '--name-only', baseline_tree, final_tree).decode().splitlines())
        require(incremental == allowed, f'Unexpected {kind} incremental scope')
    with temporary_index(source) as index:
        observed_tree, observed_edits = observe_worktree(source, index)
    if observed_tree != final_tree:
        differences = git(source, 'diff-tree', '--no-commit-id', '--name-status',
                          '-r', final_tree, observed_tree).decode()
        require(False, f'{kind} complete observed source differs from exact locked patch replay: '
                f'{observed_tree} != {final_tree}; differences:\n{differences[:12000]}')
    for relative, value in expected['source_sha256'].items():
        path = source / relative
        content = path.read_bytes() if path.is_file() else None
        require((digest(content) if content is not None else None) == value,
                f'{kind} final source mismatch: {relative}')
    return {'base_commit': expected['base_commit'], 'baseline_tree': baseline_tree,
            'source_tree': final_tree, 'observed_tree': observed_tree,
            'incremental_changed_files': allowed, 'observed_changed_files': observed_edits,
            'complete_locked_patch_replay_matches': True}


def run_contracts(lock, sdk_source, ffmpeg_source, cc, output):
    require(lock['contracts'], 'At least one actual C contract is required')
    output.mkdir(parents=True, exist_ok=False)
    substitutions = {'sdk_source': str(sdk_source.resolve()), 'ffmpeg_source': str(ffmpeg_source.resolve()),
                     'cc': cc, 'output_dir': str(output.resolve())}
    results = []
    for index, contract in enumerate(lock['contracts']):
        script = checked_file(contract)
        command = [sys.executable, str(script), *[part.format_map(substitutions) for part in contract['args']]]
        timeout = contract.get('timeout_seconds', 120)
        require(1 <= timeout <= 300, 'Invalid contract timeout')
        result = subprocess.run(command, capture_output=True, timeout=timeout)
        (output / f'contract-{index}.stdout.log').write_bytes(result.stdout)
        (output / f'contract-{index}.stderr.log').write_bytes(result.stderr)
        results.append({'command': command, 'exit': result.returncode})
        require(result.returncode == 0, f'Actual C contract failed: {script.name}; see {output}')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--variant', choices=['main', 'atmos'])
    parser.add_argument('--archive-source', action='store_true')
    parser.add_argument('--sdk-source', type=Path)
    parser.add_argument('--ffmpeg-source', type=Path)
    parser.add_argument('--cc')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'PRESELECTIONS_SOURCE_FAILED', 'runtime_verified': False}
    try:
        lock = json.loads((HERE / 'source-lock.json').read_bytes())['av3a_preselections']
        validate_lock(lock)
        if args.source:
            require(args.variant is not None, '--variant is required for mpv source verification')
            require(not args.sdk_source and not args.ffmpeg_source, 'Use separate mpv and dependency gate invocations')
            result = verify_mpv(args.source, args.variant, lock, args.archive_source)
        else:
            require(args.sdk_source and args.ffmpeg_source and args.cc,
                    'Dependency verification requires SDK, FFmpeg sources and C compiler')
            result['dependencies'] = {
                'sdk': verify_dependency(args.sdk_source, 'sdk', lock),
                'ffmpeg': verify_dependency(args.ffmpeg_source, 'ffmpeg', lock),
            }
            result['contracts'] = run_contracts(lock, args.sdk_source, args.ffmpeg_source,
                                               args.cc, args.output.with_suffix(''))
            result['status'] = 'EXACT_PRESELECTIONS_DEPENDENCIES_AND_C_CONTRACT_PASS'
            result['cpu_contract_passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
