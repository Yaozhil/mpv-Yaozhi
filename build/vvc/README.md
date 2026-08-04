# VVC software decoder integration

This directory integrates Fraunhofer HHI VVdeC (`vvdec`) into the pinned
FFmpeg branch used by the Windows build.

The build keeps FFmpeg's native `vvc` decoder available as an explicit
fallback. The FFmpeg codec registration order places `libvvdec` before the
native decoder, so mpv selects `libvvdec` by default while `--vd=vvc` remains
fully usable for diagnostics or fallback.

Pinned inputs:

- `fraunhoferhhi/vvdec`
  `1fd46b0e345669648f1e94c65e9378343db4f1a0`
- The FFmpeg `libvvdec.c` wrapper under `ffmpeg/` was imported from Martin
  Eesmaa's VVCEasy FFmpeg integration at commit
  `e2ca75bcfa0921ef8cf38de3c51363ae3a497c50`.

The vendored wrapper also carries local lifecycle and metadata hardening:
allocator plane bounds are checked against the real pool count, partial
initialization is cleanup-safe, failed flush recreation cannot call through a
null decoder, plane-buffer reference failures cannot expose freed image data,
error cleanup has a single owner for each allocation, invalid timestamps are
not marked valid, and mastering-display metadata no longer prevents
content-light metadata from being exported.

Only the wrapper, decoder registration, and native-decoder preference are
included. The wrapper uses the pinned FFmpeg branch's existing CBS H.266
implementation for VVC extradata and parameter sets; Martin's obsolete
standalone parser helpers are intentionally not compiled. The AVS2/AVS3 and
AV3A patches are kept in their existing order and are not replaced by
Martin's full FFmpeg branch.
