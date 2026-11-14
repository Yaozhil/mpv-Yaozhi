"""Apply only the reviewed migration layer to the exact official release tree."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent


def git(root, *args, env=None):
    process = subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', str(root), *args],
                             capture_output=True, text=True, timeout=120, env=env)
    if process.returncode:
        raise RuntimeError(process.stderr[-6000:])
    return process.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('variant', choices=['main', 'atmos'])
    args = parser.parse_args()
    source = args.source.resolve()
    lock = json.loads((HERE / 'migration-lock.json').read_bytes())
    row = lock['variants'][args.variant]
    patch = HERE / row['patch']
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == row['patch_sha256'], 'Reviewed patch changed'
    assert git(source, 'rev-parse', 'HEAD') == lock['upstream_commit'], 'Wrong official base'
    assert git(source, 'rev-parse', 'HEAD^{tree}') == lock['upstream_tree'], 'Wrong official tree'
    assert not git(source, 'status', '--porcelain'), 'Dirty source before applying reviewed layer'
    git(source, 'apply', '--check', '--binary', str(patch))
    git(source, 'apply', '--index', '--binary', str(patch))
    actual = git(source, 'write-tree')
    assert actual == row['source_tree'], ('Migrated source tree differs', actual, row['source_tree'])
    env = dict(os.environ, GIT_AUTHOR_DATE=lock['source_commit_date'], GIT_COMMITTER_DATE=lock['source_commit_date'])
    git(source, '-c', 'user.name=mpv-Yaozhi migration', '-c', 'user.email=build@localhost',
        'commit', '--quiet', '-m', 'Preserve reviewed Yaozhi features on mpv 0.42.0 (' + args.variant + ')', env=env)
    assert not git(source, 'status', '--porcelain'), 'Source not clean after reviewed commit'
    result = {'status': 'PASS_REVIEWED_042_PATCH_TREE', 'variant': args.variant,
              'upstream_commit': lock['upstream_commit'], 'source_tree': actual,
              'commit': git(source, 'rev-parse', 'HEAD'), 'patch_sha256': row['patch_sha256']}
    (source.parent / ('mpv-042-applied-' + args.variant + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
