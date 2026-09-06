"""Export the reviewed Omniphony delta over the shipped main-core patch stack."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--main-base', required=True)
parser.add_argument('--main-mailbox', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / 'build/atmos/parity'
out.mkdir(parents=True, exist_ok=True)
mailbox = args.main_mailbox.read_bytes().replace(b'\r\n', b'\n')
assert mailbox.count(b'\nSubject: ') == 17, 'Main-core stack must retain all 17 patches'
(out/'main-core.patch').write_bytes(mailbox)
delta = subprocess.check_output([
    'git', '-C', str(args.source), 'diff', '--ignore-space-at-eol',
    args.main_base, 'HEAD', '--', '.', ':(exclude).github',
]).replace(b'\r\n', b'\n')
assert b'new file mode' in delta and b'common/orender_dl.c' in delta
header = b'''From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: mpv-Yaozhi <build@localhost>
Date: Mon, 7 Sep 2026 12:00:00 +0800
Subject: [PATCH] Add current Omniphony renderer and ASIO over the complete main core

Integrate mgth/mpv-omniphony 6b474e387d30fabec8927880a25075f288d675d3
patches-master 0001-0028. Preserve the main core's native/unknown channel
mapping fix instead of overwriting it with the overlapping 9001 patch.
Original source authors and copyright notices are retained in the files.
Build-only upstream CI additions are excluded.
---
'''
(out/'mpv-9100-omniphony-parity.patch').write_bytes(header+delta)
lock = {
    'status': 'source-prepared-not-built',
    'mpv_base': 'c318236b8882af860f16f936225430ad053a2179',
    'main_patch_count': 17,
    'omniphony_integration': '6b474e387d30fabec8927880a25075f288d675d3',
    'engine_version': 'v0.5.2',
    'engine_commit': 'f9a79721af64ad9c39042d4deded158b568fc598',
    'asio_sdk_commit': '496a0765b8bb9c26f764f22f9a9712a937177db2',
    'libbluray_commit': '065247e5ef40ccf39857db81e2c1368354a23ef8',
    'libvpl_commit': '674d015bcb294bc39fa276e99a652ea045423e82',
    'patches': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.glob('*.patch'))},
    'common_patches': {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ['build/bluray-menu/patches/0004-hdmv-extended-ig-pid.patch',
                     'build/bluray-menu/patches/0005-hdmv-overlay-video-ready.patch']},
    'integration_notes': [
        '0012/0015 preserve main VDCTRL_SET_EXTRA_HW_FRAMES while adding/removing the temporary fallback enum.',
        '9001 is superseded: main keeps both unknown input and output layouts unspecified and preserves native_equal_layout.',
        'LF normalization affects patch transport only; upstream workflow files are excluded.',
        'No Atmos executable, launcher, engine, bridge or user configuration has been replaced.',
    ],
}
(out/'source-lock.json').write_text(json.dumps(lock, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'result':'PREPARED', 'patches':lock['patches']}))
