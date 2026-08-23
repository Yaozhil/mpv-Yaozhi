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
- `ffmpeg-hevc-dovi-rpu-scan.patch` backports upstream commit
  `89bdd9e1a50735be7478ab8c07303f3d2fe59d85`. It finds a Dolby Vision RPU
  before a trailing suffix-SEI NAL instead of assuming the RPU is always the
  final NAL in the access unit; without it a valid BL/EL pair can still render
  as base-layer-only after opening or seeking an M2TS title.
- `ffmpeg-hevc-missing-ref-foll.patch` backports upstream commit
  `265d39e551956d911a0c1c52bff5186a6bae660e`. It always synthesizes missing
  `ST_FOLL`/`LT_FOLL` reference pictures as required by HEVC section 8.3.3,
  covering follower-picture reconstruction without changing ordinary streams.
- `ffmpeg-hevc-dovi-el-seek.patch` completes arbitrary-seek recovery for the
  virtual Profile 7 enhancement-layer decoder. It enables complete reference
  recovery only when the Dolby Vision configuration explicitly says EL is
  present and BL is absent; normal HEVC, the selectable base layer, HDR10, and
  non-Profile-7 streams retain the standard decoder policy.
- `ffmpeg-mpegts-dovi-stream-group.patch` adapts official FFmpeg commit
  `29bc8ec8d15493abf3bcbdea68b3046d150334e5` to the pinned baseline, with the
  failed stream-group insertion path stopped immediately after cleanup. It
  turns the explicit Profile 7 MPEG-TS dependency PID (and the UHD Blu-ray
  `0x1011`/`0x1015` convention) into the layered-video stream group already
  consumed by mpv's FEL path. It never pairs arbitrary HEVC tracks.
- `ffmpeg-dovi-dual-track-stream-group.patch` backports the official MP4
  layered-video stream group and `vdep` reference parsing required for
  Profile 7 files that store BL and EL in separate tracks. Only the
  libavformat micro version is advanced, avoiding unrelated API gates.
- `mpv-dovi-stream-group-backport-version.patch` enables mpv's existing
  Dolby Vision layered-video handler for that exact backport version while
  leaving its newer LCEVC API guard unchanged. It also exposes the EL-owned
  Profile/Level metadata on the selectable BL track so the UI reports Dolby
  Vision instead of HDR10 after the pair is formed.
- `mpv-bluray-dovi-pair.patch` uses libbluray 1.5's authored `dv_streams[]`
  list to pair UHD Blu-ray Profile 7 base/enhancement PIDs when the MPEG-TS
  PMT has no generic Dolby Vision descriptor. It only accepts an unambiguous
  HEVC DV EL plus HEVC HDR10/BT.2020 primary video and never guesses from
  resolution, PID range, or track order.
- The workflow verifies the final FFmpeg binary exposes `dovi_split` and
  packages a verifier for single-track, dual-track file, and optional Blu-ray
  ISO FEL regression samples. The dual-track gates require mpv's `[el_pair]`
  filter output and Profile 7 metadata on the selectable base-layer track.
