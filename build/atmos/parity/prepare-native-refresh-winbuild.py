"""Append only the reviewed native-refresh mailbox after frozen preparation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]
TARGET = 'mpv-9309-native-refresh-video-priority.patch'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', required=True, type=Path)
    p.add_argument('--variant', required=True, choices=('main', 'atmos'))
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('native_refresh_gate', HERE/'verify-native-refresh-source.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    lock = json.loads((HERE/'native-refresh-lock.json').read_bytes())
    patch = gate.validate_lock(lock)
    packages = a.winbuild.resolve()/'packages'
    gate.require(packages.is_dir(), 'Frozen speaker preparation must run first')
    destination = packages/TARGET
    gate.require(not destination.exists(), 'Native-refresh layer already exists')
    manifest = {p.name: gate.sha(p.read_bytes()) for p in sorted(packages.glob('mpv-*.patch'))}
    gate.require(manifest and sorted(manifest)[-1] == 'mpv-9308-http-range.patch',
                 'Expected exact old patch-chain tail before native-refresh append')
    old = json.loads((HERE/'source-lock.json').read_bytes())['network_stability']['patches']
    for item, name in zip(old, ('mpv-9307-windows-paths.patch', 'mpv-9308-http-range.patch')):
        gate.require(manifest.get(name) == item['sha256'], 'Frozen network package patch differs')
    # Every existing package and its lexical application order remain intact.
    shutil.copyfile(patch, destination)
    gate.require({p.name: gate.sha(p.read_bytes()) for p in packages.glob('mpv-*.patch')
                  if p.name != TARGET} == manifest, 'An earlier package patch changed')
    report = dict(status='NATIVE_REFRESH_WINBUILD_APPENDED', variant=a.variant,
        parent_patch_manifest=manifest, appended_patch=TARGET,
        appended_patch_sha256=gate.sha(destination.read_bytes()),
        native_refresh_lock_sha256=gate.sha((HERE/'native-refresh-lock.json').read_bytes()),
        dependencies_changed=False, old_package_patches_unchanged=True)
    (a.winbuild.resolve()/'native-refresh-preparation.json').write_text(
        json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
