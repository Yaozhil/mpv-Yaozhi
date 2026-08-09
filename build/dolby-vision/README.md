# Dolby Vision Profile 7 FEL build integration

The pinned custom FFmpeg baseline does not contain FFmpeg commit
`6026988b753ebb1bd424612f40b17c0c363d8ed7`. That commit adds the
`dovi_split` bitstream filter required by mpv's Profile 7 BL/EL splitter.

- `ffmpeg-dovi-split.c` is copied verbatim from that LGPL-2.1-or-later
  FFmpeg commit.
- `ffmpeg-dovi-split-registration.patch` is the minimal registration and
  build-system subset adapted to the pinned FFmpeg baseline. Documentation
  and library version changes are intentionally not backported.
- The workflow verifies the final FFmpeg binary exposes `dovi_split` and
  the final mpv binary no longer reports a missing BSF for a generated FEL
  regression sample.
