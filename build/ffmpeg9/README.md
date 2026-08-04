# FFmpeg 9.0 playback feature backports

The release build remains pinned to the customized FFmpeg commit
`18c01ad424ca7712ef9a9d46953308efc75c4776`. Only the two FFmpeg 9.0
playback features selected for this bundle are backported, avoiding the
libavcodec 63 migration and preserving the AV3A, AVS2, AVS3 and VVC patch
chain.

## Animated WebP

`ffmpeg-animated-webp-backport.patch` combines the functional and FATE parts
of these upstream commits, rebased without release-note or library-version
changes:

- `a3d8ba6613dace8ad725808286bf82934e21512b`
- `20b009e30136cb55022ee32cfb4b2dcae1630bb4`
- `2ca634f5dba2607bedf6f07f84e16ded8debb440`
- `1572784128c18b9e50b1188e56fa42e3d1a763e8`

## HE-AAC 960 / DAB+

`ffmpeg-he-aac-960-backport.patch` is the functional part of upstream commit
`c1b19ee69f2142bb4b098936cc7421d80b3db7e4`, rebased without the Changelog
entry. It propagates the 960-frame flag through SBR parsing and uses 15 QMF
time slots instead of rejecting HE-AAC with a 960-sample core frame.

`tests/verify-ffmpeg9-playback.ps1` performs a real three-frame Animated WebP
decode through FFmpeg and mpv. The build preflight also checks the complete
HE-AAC 960 code path and rejects binaries that still contain FFmpeg's former
"SBR with 960 frame length" unsupported marker.
