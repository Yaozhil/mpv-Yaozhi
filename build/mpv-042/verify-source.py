"""Validate the official base, reviewed tree, and actual compiled artifact binding."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def run(command):
    p = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=180)
    if p.returncode:
        raise RuntimeError(p.stderr[-6000:])
    return p.stdout.strip()


def git(root, *args):
    return run(['git', '-c', 'core.autocrlf=false', '-C', root, *args])


def record(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variant', choices=['main', 'atmos'], required=True)
    p.add_argument('--prepare-preflight', action='store_true')
    p.add_argument('--work', type=Path)
    p.add_argument('--source', type=Path)
    p.add_argument('--compiled', action='store_true')
    p.add_argument('--winbuild', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    lock = json.loads((HERE / 'migration-lock.json').read_bytes())
    if a.prepare_preflight:
        assert a.work and not a.work.exists() and not a.compiled
        source = a.work.resolve()
        run(['git', 'init', str(source)])
        git(source, 'remote', 'add', 'origin', 'https://github.com/mpv-player/mpv.git')
        git(source, 'fetch', '--no-tags', '--depth=1', 'origin', lock['upstream_commit'])
        git(source, 'checkout', '--detach', 'FETCH_HEAD')
        assert git(source, 'rev-parse', 'HEAD^{tree}') == lock['upstream_tree']
        run([sys.executable, str(HERE / 'apply-reviewed-mpv.py'), str(source), a.variant])
    else:
        assert a.source
        source = a.source.resolve()
    row = lock['variants'][a.variant]
    assert git(source, 'rev-parse', 'HEAD^{tree}') == row['source_tree'], 'Source tree differs from reviewed port'
    assert git(source, 'rev-parse', 'HEAD^') == lock['upstream_commit'], 'Wrong actual upstream parent'
    assert not git(source, 'status', '--porcelain'), 'Source dirty after review'
    assert (source / 'MPV_VERSION').read_text().strip() == '0.42.0'
    git(source, 'diff', '--check', 'HEAD^', 'HEAD')
    checks = []
    for contract in lock['source_contracts']:
        if a.variant not in contract.get('variants', ['main', 'atmos']):
            continue
        text = (source / contract['path']).read_text('utf-8')
        for fragment in contract['required']:
            assert fragment in text, 'Lost private source contract: ' + contract['id'] + ' / ' + fragment
        for fragment, count in contract.get('exact_counts', {}).items():
            assert text.count(fragment) == count, 'Source contract count differs: ' + contract['id'] + ' / ' + fragment
        checks.append(contract['id'])
    result = {'status': 'PASS_REVIEWED_042_SOURCE_NOT_RUNTIME', 'variant': a.variant,
              'upstream_commit': lock['upstream_commit'], 'source_tree': row['source_tree'],
              'commit': git(source, 'rev-parse', 'HEAD'), 'source_contracts': checks,
              'migration_lock': record(HERE / 'migration-lock.json'), 'compiled': a.compiled,
              'github_run_id': os.environ.get('GITHUB_RUN_ID'),
              'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
    if a.compiled:
        assert a.winbuild
        build = a.winbuild.resolve() / 'build64'
        candidates = list(build.glob('mpv-x86_64-*/mpv.exe'))
        assert len(candidates) == 1, candidates
        binary = candidates[0]
        result['binaries'] = [record(binary), record(binary.with_name('mpv.com'))]
        assert all(r['bytes'] > 0 for r in result['binaries'])
        result['build_configuration'] = []
        for name in ['config.h', 'meson-log.txt', 'intro-buildoptions.json', 'intro-dependencies.json']:
            found = list(build.glob('packages/mpv-prefix/src/mpv-build/**/' + name))
            assert len(found) == 1, (name, found)
            result['build_configuration'].append(record(found[0]))
        result['status'] = 'PASS_COMPILED_042_SOURCE_AND_BINARY_BINDING_NOT_PLAYBACK'
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
