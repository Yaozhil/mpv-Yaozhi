"""Verify the exact final round-two source layer without relaxing old gates.

This gate checks complete parent/final trees, the four changed source files,
and an independent index-only replay of the packaged incremental patch. The
caller runs historical gates on the returned parent and restores this final
commit before building. A second invocation binds the retained compiled source
checkout to the produced binary hashes; runtime behavior is checked separately.
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
SOURCE_FILES = ('demux/demux_mkv.c', 'player/javascript.c', 'player/lua.c', 'sub/sd_ass.c')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(source, *args, index=None):
    env = os.environ.copy()
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    return subprocess.check_output(
        ['git', '-C', str(source), '-c', 'core.autocrlf=false', *args],
        env=env, timeout=90,
    )


def checked_file(config, relative, expected):
    path = (config / relative).resolve()
    require(path.is_relative_to(config), 'Input path escapes configuration: ' + relative)
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None, 'Invalid input digest: ' + relative)
    require(sha(path.read_bytes()) == expected, 'Input digest mismatch: ' + relative)
    return path


def validate_lock(lock, config=CONFIG):
    require(lock['version'] == 1, 'Review a new round-two schema version')
    layer = lock['patch']
    require(sorted(layer['changed_files']) == list(SOURCE_FILES), 'Round-two scope must be exactly the four approved files')
    patch = checked_file(config, layer['path'], layer['sha256'])
    records = git(config, 'apply', '--numstat', '-z', str(patch)).split(b'\0')
    paths = []
    for record in records:
        if not record:
            continue
        fields = record.split(b'\t', 2)
        require(len(fields) == 3 and fields[2], 'Renamed or malformed patch path is not allowed')
        path = fields[2].decode('utf-8')
        require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe patch path: ' + path)
        paths.append(path)
    require(sorted(paths) == list(SOURCE_FILES), 'Packaged patch scope differs from the approved four files')
    require(set(lock['variants']) == {'main', 'atmos'}, 'Both exact variant identities are required')
    for variant, expected in lock['variants'].items():
        for key in ('baseline_tree', 'source_tree', 'archive_baseline_tree', 'archive_source_tree'):
            require(re.fullmatch('[0-9a-f]{40}', expected[key]) is not None,
                    'Invalid complete tree identity: ' + variant + '/' + key)
        for key in ('before_source_sha256', 'source_sha256'):
            require(set(expected[key]) == set(SOURCE_FILES), 'Incomplete source digest set: ' + variant + '/' + key)
            require(all(re.fullmatch('[0-9a-f]{64}', value) for value in expected[key].values()),
                    'Invalid source digest: ' + variant + '/' + key)
    require(lock['tools_sha256'], 'Round-two tool identities are required')
    for path, expected in lock['tools_sha256'].items():
        checked_file(config, path, expected)
    return patch


def verify(source, variant, lock, archive_source=False, binaries=(), config=CONFIG):
    source = source.resolve()
    config = config.resolve()
    patch = validate_lock(lock, config)
    require(not git(source, 'status', '--porcelain').strip(), 'Final mpv source must be clean')
    final = git(source, 'rev-parse', 'HEAD').decode().strip()
    parent = git(source, 'rev-parse', 'HEAD^').decode().strip()
    final_tree = git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    parent_tree = git(source, 'rev-parse', 'HEAD^^{tree}').decode().strip()
    expected = lock['variants'][variant]
    prefix = 'archive_' if archive_source else ''
    require(parent_tree == expected[prefix + 'baseline_tree'], 'Unexpected complete round-two parent tree')
    require(final_tree == expected[prefix + 'source_tree'], 'Unexpected complete round-two final tree')
    changed = sorted(git(source, 'diff', '--name-only', parent, final).decode().splitlines())
    require(changed == list(SOURCE_FILES), 'Unexpected incremental source scope: ' + repr(changed))
    for path in SOURCE_FILES:
        before = git(source, 'show', parent + ':' + path)
        require(sha(before) == expected['before_source_sha256'][path], 'Baseline source mismatch: ' + path)
        require(sha((source / path).read_bytes()) == expected['source_sha256'][path], 'Final source mismatch: ' + path)
    # Replay bytes against the exact parent, preserving all unchanged paths
    # and Git modes. Neither the source worktree nor its real index is edited.
    with tempfile.TemporaryDirectory(prefix='round2-source-index-') as folder:
        index = Path(folder) / 'index'
        git(source, 'read-tree', parent, index=index)
        git(source, 'apply', '--cached', '--check', str(patch), index=index)
        git(source, 'apply', '--cached', str(patch), index=index)
        replay_tree = git(source, 'write-tree', index=index).decode().strip()
    require(replay_tree == final_tree, 'Final tree differs from exact packaged patch replay')
    binary_items = []
    for binary in binaries:
        path = binary.resolve()
        require(path.is_file() and path.stat().st_size > 0, 'Missing compiled artifact: ' + str(path))
        binary_items.append({'path': str(path), 'sha256': sha(path.read_bytes()), 'size': path.stat().st_size})
    return {
        'status': 'EXACT_ROUND2_FINAL_SOURCE_AND_PATCH_REPLAY_PASS', 'variant': variant,
        'source_commit': final, 'source_tree': final_tree,
        'baseline_commit': parent, 'baseline_tree': parent_tree,
        'packaged_patch_sha256': lock['patch']['sha256'], 'patch_replay_tree': replay_tree,
        'changed_files': list(SOURCE_FILES), 'source_sha256': expected['source_sha256'],
        'all_other_tracked_source_unchanged': True,
        'source_mode': 'windows-archive' if archive_source else 'canonical-git-checkout',
        'bound_binary_artifacts': binary_items,
        'runtime_verified': False, 'performance_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--variant', required=True, choices=['main', 'atmos'])
    parser.add_argument('--archive-source', action='store_true')
    parser.add_argument('--binary', action='append', default=[], type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = {'status': 'ROUND2_SOURCE_FAILED', 'runtime_verified': False}
    try:
        lock = json.loads((HERE / 'source-lock.json').read_bytes())['round2_stability']
        result = verify(args.source, args.variant, lock, args.archive_source, args.binary)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
