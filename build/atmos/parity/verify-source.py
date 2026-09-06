"""Apply both patch layers to a fresh archive of the exact upstream base."""
import argparse
import json
import subprocess
import tarfile
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--archive',type=Path,required=True)
parser.add_argument('--work',type=Path,required=True)
parser.add_argument('--inspect-existing',action='store_true')
args=parser.parse_args()
here=Path(__file__).resolve().parent
args.work.mkdir(parents=True,exist_ok=True)
source=args.work/'mpv-c318236b8882af860f16f936225430ad053a2179'
if not args.inspect_existing:
    assert not source.exists(), 'Verification source must be new'
    with tarfile.open(args.archive) as archive:
        archive.extractall(args.work,filter='data')
def git(*command):
    result=subprocess.run(['git','-C',str(source),'-c','core.autocrlf=false',
        '-c','user.name=Local verification','-c','user.email=verification@localhost',*command],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(result.stdout.decode(errors='replace'))
    return result.stdout.decode(errors='replace')
if not args.inspect_existing:
    git('init')
    git('add','.')
    git('commit','-m','Exact upstream source snapshot')
    git('am','--3way',str(here/'main-core.patch'))
    git('am','--3way',str(here.parents[2]/'build/bluray-menu/patches/0005-hdmv-overlay-video-ready.patch'))
    git('am','--3way',str(here/'mpv-9100-omniphony-parity.patch'))
assert git('rev-list','--count','HEAD').strip()=='20'
assert 'Add current Omniphony renderer and ASIO' in git('log','-1','--format=%s')
assert not git('status','--porcelain').strip()
text=(source/'filters/f_swresample.c').read_text(encoding='utf-8')
assert 'native_equal_layout' in text
assert 'mp_chmap_to_av_layout(&out_layout, &map_out)' in text
assert 'VDCTRL_SET_EXTRA_HW_FRAMES' in (source/'filters/f_decoder_wrapper.h').read_text(encoding='utf-8')
assert 'p->dl->output_latency_samples(p->renderer)' in (source/'audio/decode/ad_orender.c').read_text(encoding='utf-8')
assert 'visible && !await_video' in (source/'player/discnav.c').read_text(encoding='utf-8')
result={'result':'PASS','scope':'fresh exact source + 17 main patches + HDMV video-ready patch + 28-patch renderer delta',
        'source':str(source),'compiled':False}
(args.work/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
