"""Verify the exact, independently reversible round-one layers after HOLD.

The old source gates still run on their original baseline checkout. This gate
binds the added layers, their complete diff scope, variant hashes and real C
fallback/probe contract tests; it does not claim runtime performance.
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


def verify(source, variant, archive_source=False):
    source = source.resolve()
    lock = json.loads((HERE / 'source-lock.json').read_bytes())['round1_vc1_and_script_api']
    layers = lock['patches']
    assert len(layers) == 5, 'Review any change to the five independently reversible groups'
    assert not git(source, 'status', '--porcelain').strip(), 'Source must be clean'
    final = git(source, 'rev-parse', 'HEAD').decode().strip()
    baseline = git(source, 'rev-parse', f'HEAD~{len(layers)}').decode().strip()
    actual_tree = git(source, 'rev-parse', baseline + '^{tree}').decode().strip()
    tree_key = 'archive_baseline_tree' if archive_source else 'baseline_tree'
    expected_tree = lock['variants'][variant][tree_key]
    assert actual_tree == expected_tree, ('Unexpected complete baseline tree', actual_tree, expected_tree, tree_key)
    allowed = sorted({name for layer in layers for name in layer['changed_files']})
    changed = sorted(git(source, 'diff', '--name-only', baseline, final).decode().splitlines())
    assert changed == allowed, ('Unexpected source scope', changed, allowed)
    expected = lock['variants'][variant]
    assert set(expected['before_source_sha256']) == set(allowed)
    assert set(expected['source_sha256']) == set(allowed)
    for index, layer in enumerate(layers):
        patch = (CONFIG / layer['path']).resolve()
        assert patch.is_relative_to(CONFIG)
        assert sha(patch.read_bytes()) == layer['sha256']
        commit = git(source, 'rev-parse', f'HEAD~{len(layers)-index-1}').decode().strip()
        observed = sorted(git(source, 'diff', '--name-only', commit + '^', commit).decode().splitlines())
        assert observed == sorted(layer['changed_files']), (layer['path'], observed)
    for path in allowed:
        before = git(source, 'show', baseline + ':' + path) if expected['before_source_sha256'][path] is not None else None
        assert (sha(before) if before is not None else None) == expected['before_source_sha256'][path], path
        assert sha((source / path).read_bytes()) == expected['source_sha256'][path], path
    for path, digest in lock['tools_sha256'].items():
        assert sha((CONFIG / path).read_bytes()) == digest, path
    return {
        'status': 'EXACT_ROUND1_SOURCE_AND_SCOPE_PASS', 'variant': variant,
        'source_commit': final, 'source_tree': git(source, 'rev-parse', 'HEAD^{tree}').decode().strip(),
        'baseline_commit': baseline, 'baseline_tree': actual_tree,
        'source_mode': 'windows-archive' if archive_source else 'canonical-git-checkout',
        'changed_files': allowed, 'source_sha256': expected['source_sha256'],
        'all_other_tracked_source_unchanged': True,
        'compiled': False, 'runtime_verified': False, 'performance_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--variant', required=True, choices=['main', 'atmos'])
    parser.add_argument('--cc', required=True)
    parser.add_argument('--archive-source', action='store_true',
                        help='Explicit local archive mode; CI requires canonical Git file modes')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.source, args.variant, args.archive_source)
    cpu_output = args.output.with_suffix('')
    cpu_output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, str(HERE / 'verify-vc1-round1.py'),
               '--source', str(args.source.resolve()), '--cc', args.cc,
               '--output', str(cpu_output.resolve())]
    result['cpu_contract_output'] = str(cpu_output)
    try:
        subprocess.run(command, check=True, timeout=120)
        result['cpu_contract_passed'] = True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        result['status'] = 'ROUND1_CPU_CONTRACT_FAILED'
        result['cpu_contract_passed'] = False
        result['error'] = str(error)
        raise
    finally:
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
