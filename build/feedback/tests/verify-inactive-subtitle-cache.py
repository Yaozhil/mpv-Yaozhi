"""Exercise real MKV demux cache pressure while an external subtitle is selected.

All fixtures, logs and resume files are confined to a new output directory.
The baseline must terminate early; the repaired core must reach actual media EOF.
"""
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--core', type=Path, required=True)
parser.add_argument('--ffmpeg', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--expect', choices=['early-eof', 'complete'], required=True)
parser.add_argument('--fixture', type=Path)
parser.add_argument('--tracks', type=int, default=12)
args = parser.parse_args()
assert 2 <= args.tracks <= 128
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
duration = 180

def stamp(t):
    return f'{t//3600:02}:{t//60%60:02}:{t%60:02},000'

if args.fixture:
    media = args.fixture.resolve()
else:
    subs = []
    for index in range(args.tracks):
        path = out / f'inactive-{index}.srt'
        events = []
        for t in range(duration):
            # A valid, deliberately data-heavy subtitle track. Unselected packets
            # exercise the same demux accounting as image subtitles without GPU IO.
            payload = f'track {index} event {t} ' + ('subtitle cache fixture ' * 80)
            events.append(f'{t+1}\n{stamp(t)} --> {stamp(t+1)}\n{payload}\n')
        path.write_text('\n'.join(events), encoding='utf-8')
        subs.append(path)
    media = out / 'many-embedded.mkv'
    command = [str(args.ffmpeg), '-nostdin', '-v', 'error', '-f', 'lavfi',
               '-i', f'color=c=gray:s=64x36:r=10:d={duration}',
               '-f', 'lavfi', '-i', f'anullsrc=r=8000:cl=mono:d={duration}']
    for path in subs:
        command += ['-i', str(path)]
    command += ['-map', '0:v', '-map', '1:a']
    for i in range(len(subs)):
        command += ['-map', f'{i+2}:s']
    command += ['-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-c:s', 'srt',
                '-t', str(duration), str(media)]
    subprocess.run(command, check=True, capture_output=True, timeout=90)

external = out / 'selected-external.ass'
external.write_text('''[Script Info]
ScriptType: v4.00+
PlayResX: 64
PlayResY: 36
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,8,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.00,0:03:00.00,Default,,0,0,0,,external subtitle selected
''', encoding='utf-8')
probe = out / 'probe.lua'
result = out / 'result.json'
probe.write_text('''local mp=require 'mp'
local u=require 'mp.utils'
local data={}
mp.add_hook('on_unload',10,function()
 data.time_pos=mp.get_property_number('time-pos')
 data.duration=mp.get_property_number('duration')
 data.eof=mp.get_property_bool('eof-reached')
 data.cache=mp.get_property_native('demuxer-cache-state')
 data.tracks=mp.get_property_native('track-list')
end)
mp.register_event('end-file',function(e)
 data.reason=e.reason;data.error=e.error
 local f=assert(io.open(mp.get_opt('result'),'wb'))
 f:write(u.format_json(data));f:close()
 mp.commandv('quit')
end)
mp.add_timeout(60,function() mp.commandv('quit','9') end)
''', encoding='utf-8')
command = [str(args.core.resolve()), '--no-config', '--load-scripts=no',
           '--load-stats-overlay=no', '--load-auto-profiles=no', '--load-console=no',
           '--load-select=no', '--load-positioning=no', '--load-commands=no',
           '--load-context-menu=no', '--osc=no', '--ytdl=no', '--media-controls=no',
           '--vo=null', '--ao=null', '--ao-null-untimed=yes', '--untimed=yes',
           '--hwdec=no', '--demuxer-max-bytes=2MiB', '--demuxer-max-back-bytes=0',
           '--demuxer-readahead-secs=1', '--cache-secs=1', '--sub-auto=no',
           f'--sub-file={external}', f'--script={probe}',
           f'--script-opts=result={result.as_posix()}', f'--log-file={out / "player.log"}',
           '--msg-level=all=warn,cplayer=debug,demux=debug,mkv=debug', str(media)]
run = subprocess.run(command, capture_output=True, timeout=75)
(out / 'console.txt').write_bytes(run.stdout + run.stderr)
assert run.returncode == 0, (run.returncode, (run.stdout+run.stderr)[-2500:])
data = json.loads(result.read_text(encoding='utf-8'))
log = (out / 'player.log').read_text(encoding='utf-8', errors='replace')
assert data.get('reason') == 'eof', data
selected = [t for t in data['tracks'] if t['type'] == 'sub' and t.get('selected')]
assert len(selected) == 1 and selected[0].get('external'), selected
assert len([t for t in data['tracks'] if t['type']=='sub' and not t.get('external')]) == args.tracks
position = data.get('time_pos', 0)
if args.expect == 'early-eof':
    assert position < duration * .8, data
    assert 'Too many packets in the demuxer packet queues' in log
else:
    assert position >= duration - 1, data
    assert 'Too many packets in the demuxer packet queues' not in log
summary = dict(expect=args.expect, position=position, duration=data['duration'],
               embedded_tracks=args.tracks, external_selected=True, result='PASS',
               core=str(args.core), fixture=str(media))
(out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
print(json.dumps(summary))
