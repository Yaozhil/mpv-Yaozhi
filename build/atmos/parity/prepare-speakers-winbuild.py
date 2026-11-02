"""Append the fixed AV3A speaker dependency after the frozen network setup."""
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
LIBRARY_COMMIT = 'd149ed9744fd399b835c6f2920511f8cbcfce5ea'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError('Review exact '+label+' anchor')
    return text.replace(old, new, 1)

def checked_config(relative, expected):
    path=(CONFIG/relative).resolve()
    if not path.is_relative_to(CONFIG) or sha(path)!=expected:
        raise ValueError('Frozen speaker input differs: '+relative)
    return path

def prepare_speaker_layer(winbuild, lock):
    layer=lock['av3a_speakers']
    recipe_rel='build/av3a/libspatialaudio.cmake'
    recipe=checked_config(recipe_rel, layer['tools_sha256'][recipe_rel])
    if ('GIT_TAG '+LIBRARY_COMMIT+'\n') not in recipe.read_text(encoding='utf-8'):
        raise ValueError('Fixed libspatialaudio commit missing')
    patch_item=layer['patches']['ffmpeg']
    patch=checked_config(patch_item['path'],patch_item['sha256'])
    packages=winbuild.resolve()/'packages'
    package_list=packages/'CMakeLists.txt'
    ffmpeg=packages/'ffmpeg.cmake'
    old_packages=package_list.read_text(encoding='utf-8')
    old_ffmpeg=ffmpeg.read_text(encoding='utf-8')
    if ('    libspatialaudio\n' in old_packages or
        'libarcdav3a-speakers.patch' in old_ffmpeg or
        (packages/'libspatialaudio.cmake').exists() or
        (packages/'ffmpeg-9011-libarcdav3a-speakers.patch').exists()):
        raise ValueError('Speaker layer already exists; refuse repeated preparation')
    new_packages=once(old_packages,'    avs3-audiodec\n',
        '    libspatialaudio\n    avs3-audiodec\n','AV3A package list')
    new_ffmpeg=once(old_ffmpeg,'        avs3-audiodec\n',
        '        libspatialaudio\n        avs3-audiodec\n','FFmpeg AV3A dependency')
    # Append after every existing FFmpeg patch; none of their ordering changes.
    last_patch=(
        '        COMMAND ${EXEC} git apply --check ${CMAKE_CURRENT_SOURCE_DIR}/ffmpeg-9010-truehd-mat-padding.patch\n'
        '        COMMAND ${EXEC} git apply ${CMAKE_CURRENT_SOURCE_DIR}/ffmpeg-9010-truehd-mat-padding.patch\n')
    new_patch=(
        '        COMMAND ${EXEC} git apply --check ${CMAKE_CURRENT_SOURCE_DIR}/ffmpeg-9011-libarcdav3a-speakers.patch\n'
        '        COMMAND ${EXEC} git apply ${CMAKE_CURRENT_SOURCE_DIR}/ffmpeg-9011-libarcdav3a-speakers.patch\n')
    new_ffmpeg=once(new_ffmpeg,last_patch,last_patch+new_patch,'last frozen FFmpeg patch')
    new_ffmpeg=once(new_ffmpeg,'    BUILD_COMMAND ${MAKE}\n',
        '    BUILD_COMMAND ${MAKE} V=1\n','actual verbose FFmpeg compile/link logging')
    # Prepare every replacement in memory before changing the generated tree.
    shutil.copyfile(recipe,packages/'libspatialaudio.cmake')
    shutil.copyfile(patch,packages/'ffmpeg-9011-libarcdav3a-speakers.patch')
    package_list.write_text(new_packages,encoding='utf-8',newline='\n')
    ffmpeg.write_text(new_ffmpeg,encoding='utf-8',newline='\n')
    tools=winbuild.resolve()/'speaker-lock-tools'
    for relative in ('build/atmos/parity/source-lock.json',
                     'build/atmos/parity/verify-dependency-build.py',
                     'build/av3a/libspatialaudio.cmake'):
        target=tools/'config'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(CONFIG/relative,target)
    shutil.copyfile(HERE/'verify-speakers-build.py',tools/'verify-speakers-build.py')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild',type=Path,required=True)
    p.add_argument('--variant',choices=['main','atmos'],required=True)
    p.add_argument('--asio-sdk',type=Path)
    a=p.parse_args()
    lock=json.loads((HERE/'source-lock.json').read_bytes())
    setup=HERE/'prepare-network-winbuild.py'
    expected=lock['network_stability']['tools_sha256'][setup.relative_to(CONFIG).as_posix()]
    if sha(setup)!=expected:
        raise ValueError('Frozen network setup changed')
    # Validate new inputs before the old setup mutates generated package files.
    layer=lock['av3a_speakers']
    for rel in ('build/av3a/libspatialaudio.cmake',):
        checked_config(rel,layer['tools_sha256'][rel])
    item=layer['patches']['ffmpeg']; checked_config(item['path'],item['sha256'])
    cmd=[sys.executable,'-B',str(setup),'--winbuild',str(a.winbuild),'--variant',a.variant]
    if a.asio_sdk:cmd.extend(['--asio-sdk',str(a.asio_sdk)])
    subprocess.run(cmd,check=True,timeout=180)
    prepare_speaker_layer(a.winbuild,lock)
    print('SPEAKERS_WINBUILD_PREPARED variant='+a.variant)

if __name__=='__main__':main()
