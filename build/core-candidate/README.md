# Core candidate backports

These patches keep both published core baselines pinned and backport only the
selected upstream fixes. They intentionally do not replace the private AV3A,
VVDEC, SDL spatial-audio, Dolby Vision FEL, HDR Vivid, image-subtitle, or
Omniphony patch stacks.

## Main core (`mpv@99b4c12`, `llawsxx/FFmpeg@18c01ad4`)

Applied after the existing private patches:

- `main-9900`: independent secondary subtitle scaling (`8ab3f8b66d`)
- `main-9901`..`main-9904`: curl Range consistency and discarded-read interruption
  (`8849c4963`, `5910e9c2b`, `762c5999c`, `48e6c35c0`)
- `main-9905` + `main-9905-hwdec`: VO frame-retention accounting followed by
  VO-derived hardware-decoder surface pool sizing (`7f72f64b7`, `24c1cc52a`)
- `main-9906`: recreate the SPDIF muxer on decoder reset (`1388a4539`)
- `ffmpeg-8800`: preserve TrueHD MAT padding across branches (`2db563fac2`)

## Atmos sidecar (`mpv@8c67647`, `FFmpeg@b397eba`)

The pinned Atmos base already contains `secondary-sub-scale`, and its FFmpeg
commit is a descendant of the TrueHD MAT fix. It therefore applies only the
network, paired VO/hwdec, and SPDIF patches after the Omniphony and
image-subtitle stacks. The VO frame-retention commit is a mandatory direct
prerequisite of the hwdec auto-sizing commit and is always applied first.
Its newly enabled libcurl is pinned to `curl@68720b4` (8.21.0) and built with
the native Windows Schannel/CA backend; OpenSSL, ECH, HTTP/2 and HTTP/3 remain
disabled in this sidecar to keep the added dependency surface minimal.

## Release gate

Both binaries must expose the expected option types/defaults and retain their
existing private capabilities. The candidate is not deployable when any
audio, network, D3D11VA, subtitle, FEL, AV3A/VVDEC, SDL, or Lua regression
gate fails.
