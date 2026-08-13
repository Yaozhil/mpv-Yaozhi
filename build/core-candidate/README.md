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
- `main-9905`: VO-derived hardware-decoder surface pool sizing (`24c1cc52a`)
- `main-9906`: recreate the SPDIF muxer on decoder reset (`1388a4539`)
- `ffmpeg-8800`: preserve TrueHD MAT padding across branches (`2db563fac2`)

## Atmos sidecar (`mpv@8c67647`, `FFmpeg@b397eba`)

The pinned Atmos base already contains `secondary-sub-scale`, and its FFmpeg
commit is a descendant of the TrueHD MAT fix. It therefore applies only
`mpv-8801` through `mpv-8806`, after the Omniphony and image-subtitle patches.

## Release gate

Both binaries must expose the expected option types/defaults and retain their
existing private capabilities. The candidate is not deployable when any
audio, network, D3D11VA, subtitle, FEL, AV3A/VVDEC, SDL, or Lua regression
gate fails.
