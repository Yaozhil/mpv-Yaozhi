"""Inject the audited single-hunk custom-IO fix into an isolated winbuild recipe."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil

BASE = '18c01ad424ca7712ef9a9d46953308efc75c4776'
PATCH = 'ffmpeg-9012-custom-io-failure-close.patch'
HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    root = a.winbuild.resolve()
    recipe = root / 'packages/ffmpeg.cmake'
    before = recipe.read_bytes()
    text = before.decode('utf-8-sig')
    assert re.findall(r'^\s*GIT_TAG\s+(\S+)\s*$', text, re.M) == [BASE], 'unexpected FFmpeg base'
    assert PATCH not in text, 'refuse duplicate patch injection'
    assert text.count('    CONFIGURE_COMMAND ') == 1
    old = re.findall(r'git apply \$\{CMAKE_CURRENT_SOURCE_DIR\}/(\S+)', text)
    assert len(old) >= 15 and 'ffmpeg-9011-libarcdav3a-speakers.patch' in old
    addition = ('        COMMAND ${EXEC} git apply --check ${CMAKE_CURRENT_SOURCE_DIR}/' + PATCH + '\n'
                '        COMMAND ${EXEC} git apply ${CMAKE_CURRENT_SOURCE_DIR}/' + PATCH + '\n')
    text = text.replace('    CONFIGURE_COMMAND ', addition + '    CONFIGURE_COMMAND ', 1)
    assert re.findall(r'git apply \$\{CMAKE_CURRENT_SOURCE_DIR\}/(\S+)', text) == old + [PATCH]
    patch = HERE / PATCH
    shutil.copyfile(patch, root / 'packages' / PATCH)
    recipe.write_text(text, encoding='utf-8', newline='\n')
    receipt = {'schema': 'MPV_042_FFMPEG_NESTED_IO_RECIPE_V1', 'status': 'PASS_INJECTED_NOT_BUILT',
               'base': BASE, 'upstream_fix': 'dc74fe70b28df8ff69f99b693665163bf9a6a16a',
               'recipe_before_sha256': hashlib.sha256(before).hexdigest(),
               'recipe_after_sha256': hashlib.sha256(recipe.read_bytes()).hexdigest(),
               'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
               'retained_patch_order': old, 'version_policy': 'keep fork 62.13.102; binary-bound proof gates curl'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
