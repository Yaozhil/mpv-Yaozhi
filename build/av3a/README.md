# AV3A build integration

This directory contains the reproducible build glue for first-stage AV3A /
Audio Vivid decoding in the normal Windows mpv kernel.

Pinned upstream inputs:

- `lioumin1/Sourcecodeforplayer`
  `e7d244d29454eb04c968cd98a30587303a9c15f8`
- `llawsxx/FFmpeg`
  `18c01ad424ca7712ef9a9d46953308efc75c4776`

The reference decoder is built as a static `libAVS3AudioDec.a`. FFmpeg links
that library through its `libarcdav3a` wrapper, then mpv receives normal PCM
frames from FFmpeg.

The library patch removes the CLI entry and file/WAV I/O objects, suppresses
reference-decoder console output in library mode, and uses the source tree's
embedded neural model. The upstream core still has fatal `exit()` paths for
exceptional allocation/internal-configuration failures; those are tracked as
a hardening item and are not AO-related.

`ffmpeg-av3a-multiframe-probe.patch` also handles legacy/test MPEG-TS files
whose PMT incorrectly uses MPEG audio stream type `0x04`. It requires three
complete AV3A frames at computed boundaries before overriding the MPEG audio
classification, then maps the accepted `av3a` stream probe result to
`AV_CODEC_ID_AV3A`, rather than globally remapping stream type `0x04`.

SDL is intentionally not part of this chain. It is an optional PCM audio
output backend, not an AV3A decoder dependency. Windows release builds keep
mpv's native WASAPI output as the default.
