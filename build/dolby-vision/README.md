# Dolby Vision Profile 7 FEL build integration

The pinned custom FFmpeg baseline does not contain FFmpeg commit
`6026988b753ebb1bd424612f40b17c0c363d8ed7`. That commit adds the
`dovi_split` bitstream filter required by mpv's Profile 7 BL/EL splitter.
It also predates the playback-side `hvcE` prerequisites that expose the
enhancement-layer HEVC configuration to the splitter.

- `ffmpeg-dovi-split.c` is copied verbatim from that LGPL-2.1-or-later
  FFmpeg commit.
- `ffmpeg-dovi-split-prerequisites.patch` backports the official playback
  pieces from FFmpeg commits `5f6dff5e7dbd9b1f3221f7c37225365dbf1e1038`,
  `e2cfc80f32bfb1bf79e67cec74f7c4b57fabfcde`,
  `523b9faa945bf8a69295548389c3c0151cb09251`, and
  `2c74d197eed2805bf77e9fdb0fe4eae1171ffdaa`.
- `ffmpeg-dovi-split-registration.patch` is the minimal registration and
  build-system subset adapted to the pinned FFmpeg baseline. Documentation
  and library version changes are intentionally not backported.
- The workflow verifies the final FFmpeg binary exposes `dovi_split` and
  the final mpv binary no longer reports a missing BSF for a generated FEL
  regression sample.
