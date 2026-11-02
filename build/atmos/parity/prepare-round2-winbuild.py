"""Append the round-two stability layer after the frozen AV3A setup."""
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
    lock = json.loads((HERE / 'source-lock.json').read_bytes())
    layer = lock['round2_stability']
    # Preserve the old setup's exact hash and gate boundary. The new setup has
    # its own identity in round2_stability instead of changing the AV3A pins.
    old_setup = HERE / 'prepare-winbuild.py'
    expected = lock['av3a_preselections']['tools_sha256'][old_setup.relative_to(CONFIG).as_posix()]
    assert hashlib.sha256(old_setup.read_bytes()).hexdigest() == expected, 'Frozen AV3A setup changed'
    command = [sys.executable, '-B', str(old_setup), '--winbuild', str(args.winbuild),
               '--variant', args.variant]
    if args.asio_sdk:
        command.extend(['--asio-sdk', str(args.asio_sdk)])
    subprocess.run(command, check=True, timeout=120)

    patch = (CONFIG / layer['patch']['path']).resolve()
    assert patch.is_relative_to(CONFIG), 'Round-two patch path escapes configuration'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == layer['patch']['sha256'], 'Round-two patch digest mismatch'
    packages = args.winbuild.resolve() / 'packages'
    shutil.copyfile(patch, packages / 'mpv-9306-round2-stability.patch')

    # Keep the exact mpv checkout that was compiled available for the final
    # source/binary gate. Explicit fullclean remains unchanged for cache reuse.
    helper = args.winbuild.resolve() / 'cmake/custom_steps.cmake'
    text = helper.read_text()
    old = '    if(NOT "${_name}" MATCHES "^(avs3-audiodec|ffmpeg)$")\n'
    assert text.count(old) == 1, 'Review pinned post-install source retention'
    helper.write_text(text.replace(old,
        '    if(NOT "${_name}" MATCHES "^(avs3-audiodec|ffmpeg|mpv)$")\n', 1))
    print('ROUND2_WINBUILD_PREPARED variant=' + args.variant)


if __name__ == '__main__':
    main()
