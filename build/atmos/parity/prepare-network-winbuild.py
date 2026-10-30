"""Append the Windows/HTTP layers after the frozen round-two preparation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--winbuild', type=Path, required=True)
    parser.add_argument('--variant', choices=['main', 'atmos'], required=True)
    parser.add_argument('--asio-sdk', type=Path)
    args = parser.parse_args()
    lock = json.loads((HERE/'source-lock.json').read_bytes())
    setup = HERE/'prepare-round2-winbuild.py'
    expected = lock['round2_stability']['tools_sha256'][setup.relative_to(CONFIG).as_posix()]
    if hashlib.sha256(setup.read_bytes()).hexdigest() != expected:
        raise ValueError('Frozen round-two setup changed')
    command = [sys.executable, '-B', str(setup), '--winbuild', str(args.winbuild),
               '--variant', args.variant]
    if args.asio_sdk:
        command.extend(['--asio-sdk', str(args.asio_sdk)])
    subprocess.run(command, check=True, timeout=120)
    targets = ('mpv-9307-windows-paths.patch', 'mpv-9308-http-range.patch')
    patches = lock['network_stability']['patches']
    if len(patches) != len(targets):
        raise ValueError('Windows and HTTP layers must both be present')
    for item, target in zip(patches, targets):
        patch = (CONFIG/item['path']).resolve()
        if not patch.is_relative_to(CONFIG):
            raise ValueError('Patch path escapes configuration')
        if hashlib.sha256(patch.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Network patch digest mismatch: '+item['path'])
        shutil.copyfile(patch, args.winbuild.resolve()/'packages'/target)
    print('NETWORK_WINBUILD_PREPARED variant='+args.variant)


if __name__ == '__main__':
    main()
