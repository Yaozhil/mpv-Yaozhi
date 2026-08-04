# AV3A build integration

This directory contains the reproducible build glue for AV3A / Audio Vivid
decoding and the optional spatial-rendering path in the normal Windows mpv
kernel.

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

`ffmpeg-av3a-frame-parser.patch` replaces the original packet passthrough
parser with an `FFCodecParser` backed by `ParseContext`. It calculates the
encoded frame size from the validated AV3A header and uses
`ff_combine_frame()` to assemble exact frames when MPEG-TS PES payloads split
or combine AV3A access units.

The decoder defaults to `av3a_render=native`. In this mode FFmpeg preserves
the decoder's transport-channel count, sample count, sample rate, and PCM
samples; no automatic downmix is performed. HOA transport channels use ACN
ordering. Streams explicitly identified as ACN/SN3D can use FFmpeg's
ambisonic layout; the reference decoder's metadata-free HOA transport default
is ACN/N3D, so that path intentionally uses named custom channels rather than
claiming SN3D. Object and bed-plus-object streams likewise use custom channel
layouts so object transport channels are not mislabeled as speakers.

`av3a_render=binaural` is an explicit opt-in path for object, bed-plus-object,
and HOA streams. It feeds the decoder's spatial metadata and PCM into the
bundled ByteDance renderer and returns interleaved stereo float PCM. This
renderer is a headphone/binaural renderer; it is not a general multichannel
speaker renderer. Native multichannel output remains the default until a
separate speaker-rendering backend is implemented and validated.

SDL is not part of the AV3A decode chain. The Windows build enables mpv's
maintained SDL2 audio output as an optional PCM compatibility backend, while
keeping native WASAPI first in mpv's Windows AO selection order and leaving
the release configuration on `audio-device=auto`. Selecting SDL does not
perform object/HOA rendering and does not change the decoded channel layout.

`tests/hoa-order1-128k.av3a` is a 94-frame, 48 kHz, first-order ACN/N3D HOA
validation stream. `tests/bed-object-moving.av3a` is a 281-frame, 48 kHz
stereo-bed-plus-object stream whose object transport channel is channel 2 and
whose dynamic position moves continuously across the listener. The companion
`object-metadata-probe.c` links directly to `libAVS3AudioDec.a` and requires
all 281 frames to carry dynamic metadata with at least one real object-field
change.

`tests/verify-stage2.ps1` checks that the decoder option defaults to `native`,
verifies first-frame metadata for both streams, then requires native decoding
to preserve the original 4-channel HOA and 3-channel bed-plus-object 16-bit
transport PCM. Explicit binaural rendering must produce two float channels
with the same sample count. The Windows validation compares full mpv PCM
hashes against FFmpeg reference outputs for every path, proving that native
transport channels and binaural stereo are not dropped, reordered, or
downmixed in the mpv audio chain. The native mpv checks do not force an
`audio-channels` layout, so an accidental swresample conversion cannot hide a
transport-channel regression. For this diagnostic path, mpv's raw PCM writer
accepts unknown channel layouts without assigning a speaker mask; WAV output
keeps the normal WaveExtensible layout restrictions.

The pinned davs2 fork's Windows thread handle is a 32-byte structure. Passing
it by value to `davs2_thread_join()` lets MinGW emit an aligned 256-bit stack
load even though the Windows x64 ABI only guarantees 16-byte stack alignment.
`davs2-win32-thread-join.patch` passes that structure by pointer on the native
Windows thread path while preserving the scalar POSIX `pthread_t` call.
`tests/verify-davs2-thread-close.ps1` generates a 16-byte invalid AVS2 probe
and repeatedly opens and closes `libdavs2` with 13 requested decoder threads;
the release validation rejects access-violation exits before running the
larger codec and audio regression suites.
