"""Check speaker package append order, frozen inputs and fail-before-write."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

CONFIG=Path(__file__).resolve().parents[2]
SETUP=CONFIG/'build/atmos/parity/prepare-speakers-winbuild.py'
spec=importlib.util.spec_from_file_location('speaker_setup',SETUP)
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
recipe='build/av3a/libspatialaudio.cmake'
old_patch='build/av3a/ffmpeg-libarcdav3a-preselections.patch'
lock={'av3a_speakers':{'tools_sha256':{recipe:sha(CONFIG/recipe)},
      'patches':{'ffmpeg':{'path':old_patch,'sha256':sha(CONFIG/old_patch)}}}}
results=[]

def fixture(root):
    (root/'packages').mkdir()
    (root/'cmake').mkdir()
    (root/'packages/CMakeLists.txt').write_text('set(packages\n    avs3-audiodec\n    ffmpeg\n)\n',newline='\n')
    (root/'packages/ffmpeg.cmake').write_text(
        'ExternalProject_Add(ffmpeg\n    DEPENDS\n        avs3-audiodec\n'
        '        libass\n    PATCH_COMMAND git apply old.patch\n'
        '        COMMAND ${EXEC} git apply --check ${CMAKE_CURRENT_SOURCE_DIR}/ffmpeg-9010-truehd-mat-padding.patch\n'
        '        COMMAND ${EXEC} git apply ${CMAKE_CURRENT_SOURCE_DIR}/ffmpeg-9010-truehd-mat-padding.patch\n'
        '    CONFIGURE_COMMAND original-configure\n    BUILD_COMMAND ${MAKE}\n)\n',newline='\n')
    (root/'cmake/custom_steps.cmake').write_text(
        '    if(NOT "${_name}" MATCHES "^(avs3-audiodec|ffmpeg|mpv)$")\n'
        '    ORIGINAL_POST_INSTALL_CLEANUP\n    endif()\n',newline='\n')

def all_files(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

with tempfile.TemporaryDirectory(prefix='speaker-glue-') as folder:
    root=Path(folder);fixture(root);before=all_files(root)
    setup.prepare_speaker_layer(root,lock)
    final=all_files(root)
    for name,raw in before.items():
        if name=='packages/CMakeLists.txt':
            assert final[name].replace(b'    libspatialaudio\n',b'',1)==raw
        elif name=='packages/ffmpeg.cmake':
            got=final[name].replace(b'        libspatialaudio\n',b'',1)
            lines=got.splitlines(keepends=True)
            got=b''.join(x for x in lines if b'ffmpeg-9011-libarcdav3a-speakers.patch' not in x)
            got=got.replace(b'    BUILD_COMMAND ${MAKE} V=1\n',b'    BUILD_COMMAND ${MAKE}\n',1)
            assert got==raw
        else:
            assert final[name]==raw
    assert final['packages/libspatialaudio.cmake']==(CONFIG/recipe).read_bytes()
    assert final['packages/ffmpeg-9011-libarcdav3a-speakers.patch']==(CONFIG/old_patch).read_bytes()
    assert final['packages/ffmpeg.cmake'].find(b'ffmpeg-9011-libarcdav3a-speakers.patch') > final['packages/ffmpeg.cmake'].rfind(b'ffmpeg-9010-truehd-mat-padding.patch')
    results.append('append-only-generated-package-changes')
    frozen=all_files(root)
    try:setup.prepare_speaker_layer(root,lock)
    except ValueError:pass
    else:raise AssertionError('Repeated application must reject')
    assert all_files(root)==frozen
    results.append('repeated-application-refused-without-mutation')
with tempfile.TemporaryDirectory(prefix='speaker-glue-bad-') as folder:
    root=Path(folder);fixture(root);frozen=all_files(root)
    bad=json.loads(json.dumps(lock));bad['av3a_speakers']['patches']['ffmpeg']['sha256']='0'*64
    try:setup.prepare_speaker_layer(root,bad)
    except ValueError:pass
    else:raise AssertionError('Changed patch must reject')
    assert all_files(root)==frozen
    results.append('changed-patch-refused-before-mutation')
    bad=json.loads(json.dumps(lock));bad['av3a_speakers']['tools_sha256'][recipe]='0'*64
    try:setup.prepare_speaker_layer(root,bad)
    except ValueError:pass
    else:raise AssertionError('Changed recipe must reject')
    assert all_files(root)==frozen
    results.append('changed-recipe-refused-before-mutation')
    p=root/'packages/ffmpeg.cmake';p.write_bytes(p.read_bytes().replace(b'        avs3-audiodec\n',b''))
    frozen=all_files(root)
    try:setup.prepare_speaker_layer(root,lock)
    except ValueError:pass
    else:raise AssertionError('Missing baseline anchor must reject')
    assert all_files(root)==frozen
    results.append('missing-frozen-anchor-refused-before-mutation')
print(json.dumps({'passed':True,'cases':results,'recipe_sha256':sha(CONFIG/recipe),
                  'setup_sha256':sha(SETUP)},indent=2))
