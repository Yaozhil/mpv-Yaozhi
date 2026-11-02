"""Append only the reviewed 0065 layer after unchanged native-refresh setup."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
TARGET = 'mpv-9310-native-ass-wall-progress.patch'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', required=True, type=Path)
    p.add_argument('--variant', required=True, choices=('main', 'atmos'))
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('native_freeze_gate', HERE/'verify-native-freeze-source.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    lock = json.loads((HERE/'native-freeze-lock.json').read_bytes())
    patch = gate.validate_lock(lock)
    winbuild = a.winbuild.resolve()
    packages = winbuild/'packages'
    gate.require(packages.is_dir(), 'Frozen native-refresh preparation must run first')
    manifest = {p.name: gate.sha(p.read_bytes()) for p in sorted(packages.glob('mpv-*.patch'))}
    gate.require(manifest and sorted(manifest)[-1] == 'mpv-9309-native-refresh-video-priority.patch',
        'Unexpected parent package patch-chain tail')
    old = json.loads((HERE/'native-refresh-lock.json').read_bytes())
    gate.require(manifest['mpv-9309-native-refresh-video-priority.patch'] == old['patch']['sha256'],
        'Installed parent native-refresh package differs')
    destination = packages/TARGET
    gate.require(not destination.exists(), 'Native-freeze layer already appended')
    shutil.copyfile(patch, destination)
    gate.require({p.name: gate.sha(p.read_bytes()) for p in packages.glob('mpv-*.patch')
        if p.name != TARGET} == manifest, 'An earlier package patch changed')
    report = dict(status='NATIVE_FREEZE_WINBUILD_APPENDED', variant=a.variant,
        parent_patch_manifest=manifest, appended_patch=TARGET,
        appended_patch_sha256=gate.sha(destination.read_bytes()),
        native_freeze_lock_sha256=gate.sha((HERE/'native-freeze-lock.json').read_bytes()),
        dependencies_changed=False, old_package_patches_unchanged=True,
        fontconfig_preparation_unchanged=True)
    (winbuild/'native-freeze-preparation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
