"""Install source-locked migration inputs into a newly prepared winbuild only."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--winbuild', type=Path, required=True)
    parser.add_argument('--variant', choices=['main', 'atmos'], required=True)
    args = parser.parse_args()
    root = args.winbuild.resolve()
    packages = root / 'packages'
    lock = json.loads((HERE / 'migration-lock.json').read_bytes())
    if (root / 'mpv-042-prepared.json').exists():
        raise RuntimeError('Refuse to reprepare a reviewed winbuild')
    for item in lock['input_files']:
        path = HERE / item['path']
        assert path.resolve().is_relative_to(HERE) and sha(path) == item['sha256'], 'Migration input drift: ' + item['path']
    original = {p.name: sha(p) for p in packages.glob('mpv-*.patch')}
    expected = lock['historical_package_patches'][args.variant]
    assert original == expected, 'Earlier complete 58/59 preparation differs from frozen installed baseline'
    overlays = []
    for item in lock['dependency_overlays'][args.variant]:
        source = HERE / item['path']
        target = root / item['recipe_path']
        assert sha(target) == item['original_sha256'], 'Pre-overlay recipe drift: ' + item['recipe_path']
        assert sha(source) == item['sha256'], 'Pin overlay drift'
        shutil.copyfile(source, target)
        text = target.read_text('utf-8')
        # Pinned overlays intentionally remove force_rebuild_git and its
        # floating update hooks. cleanup() still invokes reset_head.sh. Supply
        # only an ancestry assertion: preserve private git-am descendants and
        # never fetch, follow a branch, reset HEAD, or delete completion stamps.
        name = Path(item['recipe_path']).stem
        if re.search(r'\bcleanup\(' + re.escape(name) + r'\s+', text):
            pin = re.findall(r'^\s*GIT_TAG\s+([0-9a-f]{40})\s*$', text, re.M)
            assert len(pin) == 1 and 'force_rebuild_git(' not in text
            text += ('\n# Fixed-pin cleanup assertion; preserves private git-am descendants.\n'
                     f'get_property(_yaozhi_042_stamp TARGET {name} PROPERTY _EP_STAMP_DIR)\n'
                     f'get_property(_yaozhi_042_source TARGET {name} PROPERTY _EP_SOURCE_DIR)\n'
                     'file(MAKE_DIRECTORY "${_yaozhi_042_stamp}")\n'
                     'file(WRITE "${_yaozhi_042_stamp}/reset_head.sh"\n'
                     '"#!/usr/bin/env bash\\nset -euo pipefail\\n'
                     'git -C \\"${_yaozhi_042_source}\\" cat-file -e '
                     f'\\"{pin[0]}^{{commit}}\\"\\n'
                     'git -C \\"${_yaozhi_042_source}\\" merge-base --is-ancestor '
                     f'{pin[0]} HEAD\\n")\n'
                     'file(CHMOD "${_yaozhi_042_stamp}/reset_head.sh"\n'
                     '  PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)\n')
            target.write_text(text, encoding='utf-8', newline='\n')
        overlays.append({'recipe': item['recipe_path'], 'pinned_overlay_sha256': item['sha256'],
                         'effective_recipe_sha256': sha(target)})
    # Retire old mpv package files only inside this owned winbuild; all source
    # feature decisions remain in the reviewed per-patch migration ledger.
    assert packages.resolve().is_relative_to(root)
    for p in packages.glob('mpv-*.patch'):
        assert p.resolve().is_relative_to(packages)
        p.unlink()
    recipe = packages / 'mpv.cmake'
    text = recipe.read_text()
    old = '    GIT_TAG ' + lock['historical_mpv_base']
    assert text.count(old) == 1
    text = text.replace(old, '    GIT_TAG ' + lock['upstream_commit'])
    old_command = 'PATCH_COMMAND ${EXEC} git am --3way ${CMAKE_CURRENT_SOURCE_DIR}/mpv-*.patch'
    assert text.count(old_command) == 1
    command = ('PATCH_COMMAND ${EXEC} python3 ${CMAKE_CURRENT_SOURCE_DIR}/mpv-042-inputs/apply-reviewed-mpv.py '
               '<SOURCE_DIR> ' + args.variant)
    text = text.replace(old_command, command)
    recipe.write_text(text)
    dest = packages / 'mpv-042-inputs'
    assert not dest.exists()
    dest.mkdir()
    for name in ['apply-reviewed-mpv.py', 'migration-lock.json', lock['variants'][args.variant]['patch']]:
        source = HERE / name
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Keep original AV3A/DV patches and append the proven nested-IO fix.
    # CLI isolates the dependency helper's supported public entry point.
    import subprocess
    subprocess.run([sys.executable, str(HERE / 'dependencies/apply_ffmpeg_fix.py'), '--winbuild', str(root),
                    '--output', str(root / 'mpv-042-ffmpeg-recipe.json')], check=True)
    result = {'status': 'PREPARED_REVIEWED_042_WINBUILD', 'variant': args.variant,
              'historical_patch_count': len(original), 'dependency_overlays': overlays,
              'mpv_recipe_sha256': sha(recipe), 'lock_sha256': sha(HERE / 'migration-lock.json'),
              'target_commit': lock['upstream_commit']}
    (root / 'mpv-042-prepared.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
