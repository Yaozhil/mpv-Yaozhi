"""Bind the common demux cache repair to the exact replayed player source.

This gate verifies source and patch identity. Runtime playback and compiler
coverage are reported separately by their own test runners.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(source, *args):
    return subprocess.check_output(
        ['git', '-C', str(source), '-c', 'core.autocrlf=false', *args],
        timeout=60,
    )


def verify_source(source):
    source = source.resolve()
    lock = json.loads((HERE / 'source-lock.json').read_bytes())
    fix = lock['demux_inactive_subtitle_cache_fix']
    patch = (CONFIG / fix['patch']).resolve()
    assert patch.is_relative_to(CONFIG), 'Patch escaped the frozen configuration'
    assert sha(patch.read_bytes()) == fix['patch_sha256']
    assert fix['patch_sha256'] == lock['common_patches'][fix['patch']]
    changed = fix['changed_files']
    assert changed == sorted(fix['source_sha256'])
    assert set(fix['before_source_sha256']) == set(changed)
    assert not git(source, 'status', '--porcelain').strip(), 'Replay must be clean'

    # The final patch remains the historical PTS repair. Locate the demux
    # change by path instead of depending on HEAD or an incidental layer count.
    commits = {
        git(source, 'log', '-1', '--format=%H', '--', path).decode().strip()
        for path in changed
    }
    assert len(commits) == 1 and all(commits), 'Demux repair split across layers'
    commit = commits.pop()
    observed = git(source, 'diff', '--name-only', commit + '^', commit).decode().splitlines()
    assert observed == changed, ('Unexpected repair scope', observed)
    for path in changed:
        assert sha(git(source, 'show', commit + '^:' + path)) == fix['before_source_sha256'][path], path
        expected = fix['source_sha256'][path]
        assert sha(git(source, 'show', commit + ':' + path)) == expected, path
        assert sha((source / path).read_bytes()) == expected, path
    for path, digest in fix.get('preserved_source_sha256', {}).items():
        assert sha((source / path).read_bytes()) == digest, path
    for path, digest in fix.get('test_sha256', {}).items():
        candidate = (CONFIG / path).resolve()
        assert candidate.is_relative_to(CONFIG), path
        assert sha(candidate.read_bytes()) == digest, path
    return {
        'status': 'EXACT_COMMON_DEMUX_CACHE_SOURCE_AND_SCOPE_PASS',
        'source_tree': git(source, 'rev-parse', 'HEAD^{tree}').decode().strip(),
        'repair_commit': commit,
        'source_sha256': fix['source_sha256'],
        'patch_sha256': fix['patch_sha256'],
        'compiled': False,
        'runtime_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify_source(args.source)
    raw = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding='utf-8')
    print(raw, end='')


if __name__ == '__main__':
    main()
