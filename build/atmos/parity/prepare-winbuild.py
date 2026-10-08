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

# libaribcaption recently renamed its bundled MD5 symbols to aribcc_md5_*.
# Its md5.c intentionally omits that implementation when HAVE_OPENSSL is
# defined, while the new md5_helper.hpp still calls the renamed bundled
# symbols.  The old forced HAVE_OPENSSL flags therefore leave the static
# archive with unresolved aribcc_md5_* references at the FFmpeg link step.
# Use the bundled implementation for this static Windows build; this keeps
# the dependency self-contained and avoids changing the player feature set.
aribcaption=packages/'libaribcaption.cmake'
arib_text=aribcaption.read_text()
old_flags=(
    '        "-DCMAKE_C_FLAGS=\'-DHAVE_OPENSSL=1\'"\n'
    '        "-DCMAKE_CXX_FLAGS=\'-DHAVE_OPENSSL=1\'"\n'
)
if arib_text.count(old_flags) != 1:
    raise SystemExit('Expected exactly one obsolete libaribcaption HAVE_OPENSSL flag pair')
aribcaption.write_text(arib_text.replace(old_flags, '', 1))
# Common player-side HDMV transition fix, after the shared main patch and
# before the independent Atmos decoder patch. Both variants must carry it.
shutil.copyfile(root/'build/bluray-menu/patches/0005-hdmv-overlay-video-ready.patch',
                packages/'mpv-9001-hdmv-overlay-video-ready.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0006-bluray-title-resync-hdmv-context.patch',
                packages/'mpv-9002-bluray-title-resync-hdmv-context.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0007-select-late-video-enhancement-layer.patch',
                packages/'mpv-9003-select-late-video-enhancement-layer.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0009-mkv-optional-tail-tags.patch',
                packages/'mpv-9004-mkv-optional-tail-tags.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0010-secondary-ass-full-viewport.patch',
                packages/'mpv-9005-secondary-ass-full-viewport.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0011-bluray-retain-navigation-head.patch',
                packages/'mpv-9006-bluray-retain-navigation-head.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0013-dts-hd-seek-resync.patch',
                packages/'mpv-9007-dts-hd-seek-resync.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0014-bluray-slideshow-audio.patch', packages/'mpv-9008-bluray-slideshow-audio.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0015-native-timing-diagnostics.patch', packages/'mpv-9009-native-timing-diagnostics.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0016-secondary-ass-refresh.patch', packages/'mpv-9010-secondary-ass-refresh.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0017-secondary-ass-replace.patch', packages/'mpv-9011-secondary-ass-replace.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0018-secondary-ass-idle.patch', packages/'mpv-9012-secondary-ass-idle.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0019-secondary-ass-video-budget.patch', packages/'mpv-9013-secondary-ass-video-budget.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0020-secondary-ass-video-headroom.patch', packages/'mpv-9014-secondary-ass-video-headroom.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0021-secondary-ass-budget-stability.patch', packages/'mpv-9015-secondary-ass-budget-stability.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0022-native-presentation-telemetry.patch', packages/'mpv-9016-native-presentation-telemetry.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0023-native-presentation-reuse.patch', packages/'mpv-9017-native-presentation-reuse.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0024-bluray-popup-atomic-overlay.patch', packages/'mpv-9018-bluray-popup-atomic-overlay.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0025-bluray-menu-audio-resume.patch', packages/'mpv-9019-bluray-menu-audio-resume.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0026-bluray-popup-fragment-hold.patch', packages/'mpv-9020-bluray-popup-fragment-hold.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0027-bluray-menu-audio-diagnostics.patch', packages/'mpv-9021-bluray-menu-audio-diagnostics.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0028-bluray-menu-audio-queue-retain.patch', packages/'mpv-9022-bluray-menu-audio-queue-retain.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0029-bluray-audio-sample-rate.patch', packages/'mpv-9023-bluray-audio-sample-rate.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0030-secondary-ass-low-fps-budget.patch', packages/'mpv-9024-secondary-ass-low-fps-budget.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0031-secondary-ass-video-deadline.patch', packages/'mpv-9025-secondary-ass-video-deadline.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0032-dovi-rpu-enhancement-metadata.patch', packages/'mpv-9026-dovi-rpu-enhancement-metadata.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0033-player-version-brand.patch', packages/'mpv-9027-player-version-brand.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0034-secondary-ass-continuous-clock.patch', packages/'mpv-9028-secondary-ass-continuous-clock.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0037-native-ass-pacing-evidence.patch', packages/'mpv-9029-native-ass-pacing-evidence.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0038-secondary-ass-quiet-gap-hold.patch', packages/'mpv-9030-secondary-ass-quiet-gap-hold.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0039-native-ass-wait-deadline-cpu-spans.patch', packages/'mpv-9031-native-ass-wait-deadline-cpu-spans.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0040-native-ass-coherent-queue-lead.patch', packages/'mpv-9032-native-ass-coherent-queue-lead.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0041-native-ass-display-forecast-staged-queue.patch', packages/'mpv-9033-native-ass-display-forecast-staged-queue.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0042-native-ass-fixed-display-phase.patch', packages/'mpv-9034-native-ass-fixed-display-phase.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0043-native-ass-ui-probe-recovery.patch', packages/'mpv-9035-native-ass-ui-probe-recovery.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0044-native-ass-ui-lifecycle.patch', packages/'mpv-9036-native-ass-ui-lifecycle.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0045-native-ass-fixed-budget-recovery.patch', packages/'mpv-9037-native-ass-fixed-budget-recovery.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0046-native-ass-fresh-clock-continuity.patch', packages/'mpv-9038-native-ass-fresh-clock-continuity.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0047-native-ass-fresh-proposal-retry.patch', packages/'mpv-9039-native-ass-fresh-proposal-retry.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0048-native-ass-cache-window-neutral-pose.patch', packages/'mpv-9040-native-ass-cache-window-neutral-pose.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0049-native-ass-captured-submit-window.patch', packages/'mpv-9041-native-ass-captured-submit-window.patch')
# ftp.gnu.org can be unavailable from some CI egress paths. These mirrors
# were independently checked to have the same pinned SHA256; retaining
# URL_HASH means a mirror cannot silently change the dependency bytes.
iconv=packages/'libiconv.cmake'
iconv_text=iconv.read_text()
assert 'libiconv-1.18.tar.gz' in iconv_text
assert 'SHA256=3B08F5F4F9B4EB82F151A7040BFD6FE6C6FB922EFE4B1659C66EA933276965E8' in iconv_text
old_url='    URL https://ftp.gnu.org/pub/gnu/libiconv/libiconv-1.18.tar.gz\n'
new_url=(
    '    URL https://mirrors.kernel.org/gnu/libiconv/libiconv-1.18.tar.gz\n'
    '        https://ftp.nluug.nl/pub/gnu/libiconv/libiconv-1.18.tar.gz\n'
    '        https://ftp.gnu.org/pub/gnu/libiconv/libiconv-1.18.tar.gz\n'
)
assert iconv_text.count(old_url)==1
iconv_text=iconv_text.replace(old_url,new_url,1)
marker='    URL_HASH SHA256=3B08F5F4F9B4EB82F151A7040BFD6FE6C6FB922EFE4B1659C66EA933276965E8\n'
assert iconv_text.count(marker)==1
iconv_text=iconv_text.replace(marker,marker+'    TIMEOUT 120\n    INACTIVITY_TIMEOUT 30\n',1)
iconv.write_text(iconv_text)

# Apply the same pinned-byte fallback to the cold GCC binutils download.
# The GCC snapshot/compiler version and flags remain pinned unchanged.
binutils=args.winbuild.resolve()/'toolchain/gcc/gcc-binutils.cmake'
binutils_text=binutils.read_text()
old_url='    URL https://ftp.gnu.org/gnu/binutils/binutils-2.45.1.tar.xz\n'
new_url=(
    '    URL https://mirrors.kernel.org/sourceware/binutils/releases/binutils-2.45.1.tar.xz\n'
    '        https://ftp.nluug.nl/pub/gnu/binutils/binutils-2.45.1.tar.xz\n'
    '        https://ftp.gnu.org/gnu/binutils/binutils-2.45.1.tar.xz\n'
)
assert binutils_text.count(old_url)==1
binutils_text=binutils_text.replace(old_url,new_url,1)
marker='    URL_HASH SHA512=ea030419eba387579ab717be7e3223fc99e93b586860b06003c12489f93441640d4082736f76aa5e98233db4f46e232f536a45e471486de1f5b64e1b827c167e\n'
assert binutils_text.count(marker)==1
binutils_text=binutils_text.replace(marker,marker+'    TIMEOUT 120\n    INACTIVITY_TIMEOUT 30\n',1)
binutils.write_text(binutils_text)

# The workflow's common setup already pins GCC 14.4.0; check that effective
# input before providing same-byte mirrors, preserving its exact SHA512.
gcc=args.winbuild.resolve()/'toolchain/gcc/gcc.cmake'
gcc_text=gcc.read_text()
old_url='    URL https://ftp.gnu.org/gnu/gcc/gcc-14.4.0/gcc-14.4.0.tar.xz\n'
new_url=(
    '    URL https://mirrors.kernel.org/gnu/gcc/gcc-14.4.0/gcc-14.4.0.tar.xz\n'
    '        https://ftp.nluug.nl/pub/gnu/gcc/gcc-14.4.0/gcc-14.4.0.tar.xz\n'
    '        https://ftp.gnu.org/gnu/gcc/gcc-14.4.0/gcc-14.4.0.tar.xz\n'
)
assert gcc_text.count(old_url)==1, 'Expected the workflow-pinned GCC 14.4.0 source'
gcc_text=gcc_text.replace(old_url,new_url,1)
marker='    URL_HASH SHA512=725ed8bdd43ef1726ffe8b5e8615a13e247fac9575b7626ae013a2975d000ea213212dc414b2f2631ac4785c1c8beca85555222faf9904d3b2fa6a3807a83a15\n'
assert gcc_text.count(marker)==1
gcc_text=gcc_text.replace(marker,marker+'    TIMEOUT 120\n    INACTIVITY_TIMEOUT 30\n',1)
gcc.write_text(gcc_text)

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
    '        COMMAND ${EXEC} git apply '+patch+'\n'
    '        COMMAND ${EXEC} git apply --check ${CMAKE_CURRENT_SOURCE_DIR}/libbluray-9008-hdmv-link-terminate-command-list.patch\n'
    '        COMMAND ${EXEC} git apply ${CMAKE_CURRENT_SOURCE_DIR}/libbluray-9008-hdmv-link-terminate-command-list.patch\n'
    '        COMMAND ${EXEC} git apply --check ${CMAKE_CURRENT_SOURCE_DIR}/libbluray-9012-still-menu-retain-ig-tail.patch\n'
    '        COMMAND ${EXEC} git apply ${CMAKE_CURRENT_SOURCE_DIR}/libbluray-9012-still-menu-retain-ig-tail.patch\n'
    '        COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/src ${CMAKE_BINARY_DIR}/still-ig-bd-source/src\n'
    '        COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_BINARY_DIR}/menu-dv-bd-source/src/libbluray/hdmv\n'
    '        COMMAND ${CMAKE_COMMAND} -E copy <SOURCE_DIR>/src/libbluray/hdmv/hdmv_vm.c ${CMAKE_BINARY_DIR}/menu-dv-bd-source/src/libbluray/hdmv/hdmv_vm.c\n',1)
bluray.write_text(text)
shutil.copyfile(root/'build/bluray-menu/patches/0004-hdmv-extended-ig-pid.patch',
                packages/'libbluray-9004-hdmv-extended-ig-pid.patch')
shutil.copyfile(root/'build/bluray-menu/patches/0008-hdmv-link-terminate-command-list.patch',
                packages/'libbluray-9008-hdmv-link-terminate-command-list.patch')
# MinGW already supplies the secure CRT functions. An undefined _MSC_VER
# must not enable libvpl's pre-2005 MSVC macros inside Windows headers.
vpl=packages/'libvpl.cmake'
text=vpl.read_text()
assert 'PATCH_COMMAND' not in text, 'Review existing libvpl patches before composing'
assert '    GIT_TAG main\n' in text
text=text.replace('    GIT_TAG main\n',f"    GIT_TAG {lock['libvpl_commit']}\n",1)
text=text.replace('    GIT_REMOTE_NAME origin\n','',1)
assert text.count(anchor)==1
patch='${CMAKE_CURRENT_SOURCE_DIR}/libvpl-9000-mingw-secure-crt.patch'
text=text.replace(anchor,anchor+
    '    PATCH_COMMAND ${EXEC} git apply --check '+patch+'\n'
    '        COMMAND ${EXEC} git apply '+patch+'\n',1)
vpl.write_text(text)
shutil.copyfile(here/'libvpl-9000-mingw-secure-crt.patch',
                packages/'libvpl-9000-mingw-secure-crt.patch')
print('PARITY_WINBUILD_PREPARED variant='+args.variant)

shutil.copyfile(root/'build/bluray-menu/patches/0012-still-menu-retain-ig-tail.patch', packages/'libbluray-9012-still-menu-retain-ig-tail.patch')
