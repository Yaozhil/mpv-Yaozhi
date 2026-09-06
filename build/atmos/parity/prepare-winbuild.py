"""Apply variant-only configuration after the unchanged main winbuild setup."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--winbuild',type=Path,required=True)
parser.add_argument('--variant',choices=['main','atmos'],required=True)
parser.add_argument('--asio-sdk',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[3]
here=Path(__file__).resolve().parent
lock=json.loads((here/'source-lock.json').read_text(encoding='utf-8'))
packages=args.winbuild.resolve()/'packages'
for name,digest in lock['patches'].items():
    assert hashlib.sha256((here/name).read_bytes()).hexdigest()==digest, name
for name,digest in lock['common_patches'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, name
mpv=packages/'mpv.cmake'
text=mpv.read_text()
for required in ['-Dwin32-smtc=enabled','-Dlibcurl=enabled','-Dsdl2-audio=enabled','mpv-*.patch']:
    assert required in text, 'Main feature/setup missing: '+required
anchor='        -Dwin32-smtc=enabled\n'
assert text.count(anchor)==1
if args.variant=='atmos':
    assert args.asio_sdk and (args.asio_sdk/'common/asio.h').is_file()
    options='        -Dorender=enabled\n        -Dasio=enabled\n'
    options+=f'        -Dasio-sdk={args.asio_sdk.resolve().as_posix()}\n'
    shutil.copyfile(here/'mpv-9100-omniphony-parity.patch',packages/'mpv-9100-omniphony-parity.patch')
    text=text.replace(anchor,anchor+options,1)
mpv.write_text(text)
# Common player-side HDMV transition fix, after the shared main patch and
# before the independent Atmos decoder patch. Both variants must carry it.
shutil.copyfile(root/'build/bluray-menu/patches/0005-hdmv-overlay-video-ready.patch',
                packages/'mpv-9001-hdmv-overlay-video-ready.patch')
bluray=packages/'libbluray.cmake'
text=bluray.read_text()
assert 'PATCH_COMMAND' not in text, 'Review existing libbluray patches before composing'
repo='    GIT_REPOSITORY https://code.videolan.org/videolan/libbluray.git\n'
assert text.count(repo)==1
text=re.sub(r'^    GIT_TAG .*\n','',text,flags=re.M)
text=text.replace(repo,repo+f"    GIT_TAG {lock['libbluray_commit']}\n",1)
anchor='    UPDATE_COMMAND ""\n'
assert text.count(anchor)==1
patch='${CMAKE_CURRENT_SOURCE_DIR}/libbluray-9004-hdmv-extended-ig-pid.patch'
text=text.replace(anchor,anchor+
    '    PATCH_COMMAND ${EXEC} git apply --check '+patch+'\n'
    '        COMMAND ${EXEC} git apply '+patch+'\n',1)
bluray.write_text(text)
shutil.copyfile(root/'build/bluray-menu/patches/0004-hdmv-extended-ig-pid.patch',
                packages/'libbluray-9004-hdmv-extended-ig-pid.patch')
print('PARITY_WINBUILD_PREPARED variant='+args.variant)
