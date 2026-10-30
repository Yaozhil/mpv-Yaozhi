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
FONTCONFIG_COMMIT = 'b25ffeabd15b76f86c0c6736f6df2f1b89858010'
FONTCONFIG_RECIPE_SHA = 'c20c10d75476bf1f99818e5dda7644c94ae157372b9fd396c09f1b2122b006aa'


def freeze_fontconfig(packages):
    # The previous installed build recorded the patched tree. Replaying the
    # unchanged patches against this exact upstream revision reproduces it.
    # Following main instead now breaks the old fcdir.c patch.
    recipe = packages/'fontconfig.cmake'
    original = recipe.read_bytes()
    if hashlib.sha256(original).hexdigest() != FONTCONFIG_RECIPE_SHA:
        raise ValueError('Unreviewed fontconfig recipe')
    anchor = b'    GIT_TAG main\n'
    if original.count(anchor) != 1:
        raise ValueError('Fontconfig source-ref anchor differs')
    recipe.write_bytes(original.replace(anchor,
        ('    GIT_TAG '+FONTCONFIG_COMMIT+'\n').encode(), 1))
    return dict(upstream_commit=FONTCONFIG_COMMIT,
        upstream_tree='048191d4358f4b4d57c050750a6fca8c3dda6ad2',
        previous_patched_tree='4b2a40143653a0b158a374fe513e8d603e3cbe04',
        original_recipe_sha256=FONTCONFIG_RECIPE_SHA,
        pinned_recipe_sha256=hashlib.sha256(recipe.read_bytes()).hexdigest())


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
    fontconfig = freeze_fontconfig(packages)
    report = dict(status='NATIVE_REFRESH_WINBUILD_APPENDED', variant=a.variant,
        parent_patch_manifest=manifest, appended_patch=TARGET,
        appended_patch_sha256=gate.sha(destination.read_bytes()),
        native_refresh_lock_sha256=gate.sha((HERE/'native-refresh-lock.json').read_bytes()),
        dependencies_changed=False, old_package_patches_unchanged=True,
        fontconfig_previous_source_pin=fontconfig)
    (a.winbuild.resolve()/'native-refresh-preparation.json').write_text(
        json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
