# AV3A / Audio Vivid integration notes

## Scope

Current target: make the normal mpv kernel recognize AV3A / Audio Vivid tracks and decode them to PCM for basic playback.

Explicitly out of scope for the first stage:

- CogentRedTester/mpv-changerefresh integration.
- SDL audio output as an AV3A solution.
- Full object / HOA spatial rendering.

SDL is only an audio output backend. It cannot decode AV3A. The current packaged `mpv.exe` exposes `wasapi`, `openal`, `null`, and `pcm` audio outputs, which is enough for PCM playback once FFmpeg can decode the stream.

For the Windows package, WASAPI remains the default AO. SDL is reasonable for
a standalone cross-platform demo player or as a last-resort compatibility AO,
but adding it to the AV3A decoder path would add latency/device-management
surface without improving codec support.

## Source map

Local source inspected:

- `C:\Users\杳知\Desktop\AudioVivid源码\Audio_Vivid Encapsulation tools\UWA封装工具\FFmpeg-n4.4.2`
- `C:\Users\杳知\Desktop\AudioVivid源码\AVS3A_Codec_linux`
- `https://github.com/llawsxx/FFmpeg/tree/arcav3adec`
- `https://github.com/lioumin1/Sourcecodeforplayer`

The FFmpeg 4.4.2 patch tree adds AV3A recognition and packetization:

- `libavcodec/av3a.c`
- `libavcodec/av3a.h`
- `libavcodec/av3a_parser.c`
- `libavformat/av3adec.c`
- container/tag changes in `mpegts.c`, `mpegtsenc.c`, `mov.c`, `movenc.c`, `isom_tags.c`, `rawenc.c`, `codec_id.h`, `codec_desc.c`, `parsers.c`, and build files.

That patch is not a complete audio decoder. It registers `AV_CODEC_ID_AVS3_AUDIO`, parses headers, handles raw `.av3a`, MPEG-TS stream type `0xd5`, and MP4 tag `av3a`.

The actual PCM decode path is in `AVS3A_Codec_linux`:

- CLI entry: `avs3RM0Decoder/decoder.c`
- AVS3 CLI wrapper: `avs3Decoder/src/decoder.c`
- decoder init/destroy: `avs3Decoder/src/avs3_init_dec.c`
- frame bitstream loader: `avs3Decoder/src/avs3_bitstream_dec.c`
- frame decode: `avs3Decoder/src/avs3_dec.c`
- public-ish declarations: `avs3Decoder/include/avs3_prot_dec.h`
- decoder state: `avs3Decoder/include/avs3_stat_dec.h`

The `llawsxx/FFmpeg` `arcav3adec` branch is directly useful because it already contains a modern FFmpeg-side wrapper:

- `libavcodec/libarcdav3a.c`
- `libavcodec/avs3_decoder_interface.h`
- `libavcodec/av3a.h`
- `libavcodec/av3a_parser.c`
- `libavformat/av3adec.c`

Its external decoder interface is:

```c
AVS3DecoderHandle avs3_create_decoder();
void avs3_destroy_decoder(AVS3DecoderHandle hAvs3Dec);
int parse_header(AVS3DecoderHandle hAvs3Dec, unsigned char *pData,
                 int nLenIn, int isInitFrame, int *pnLenConsumed,
                 unsigned short *crc);
int avs3_decode(AVS3DecoderHandle hAvs3Dec, unsigned char *pDataIN,
                int nLenIn, unsigned char *pDataOut, int *pnLenOut,
                int *pnLenConsumed);
```

Its `configure` changes confirm the intended link model:

```sh
libarcdav3a_decoder_deps="libarcdav3a"
libarcdav3a_decoder_extralibs="-lAVS3AudioDec"
```

This means the FFmpeg patch alone is not enough. The build must also produce and install an `AVS3AudioDec` library for the same target toolchain, then enable FFmpeg with `--enable-libarcdav3a`.

`lioumin1/Sourcecodeforplayer` already contains the matching exported decoder
interface under `av3adecoder`. Its four function signatures are byte-for-byte
compatible with the declarations vendored by the `arcav3adec` FFmpeg branch.
It also embeds the neural model in `libavs3_common/model.h`, so the Windows
package does not need a runtime `/lib/model.bin` or working-directory-dependent
resource lookup.

The current CLI loop is:

1. allocate `AVS3Decoder`
2. parse the first frame header
3. `Avs3InitDecoder(...)`
4. for each frame: `ReadBitstream(...)`, `Avs3Decode(...)`, `WriteSynthData(...)`
5. destroy decoder

## Required architecture

AV3A support must be added to FFmpeg/libavcodec, because mpv gets decoders through FFmpeg. A script/config-only solution cannot make mpv decode a new codec.

The maintainable route is:

1. Use the `arcav3adec` FFmpeg branch as the primary reference for modern FFmpeg integration.
2. Build or vendor the `AVS3AudioDec` library that exports `avs3_create_decoder`, `parse_header`, `avs3_decode`, and `avs3_destroy_decoder`.
3. Patch the FFmpeg revision used by the mpv build with the AV3A codec ID, parser, demuxer, TS/MP4 tags, and `libarcdav3a` decoder.
4. Enable FFmpeg with `--enable-libarcdav3a` and make the cross linker see `-lAVS3AudioDec`.
5. Build that patched FFmpeg into the normal mpv kernel through the existing GitHub Actions build workflow.

Do not use an external decoder executable or pipe as the first implementation. That would make seeking, track switching, timestamps, errors, and future object/HOA rendering harder, and would need to be replaced later.

## Decoder wrapper shape

The AVS3A code should be wrapped behind a small internal API before touching FFmpeg-specific code:

```c
typedef struct AV3ACoreDecoder AV3ACoreDecoder;

int av3a_core_open(AV3ACoreDecoder **dec,
                   const uint8_t *extradata,
                   int extradata_size,
                   const uint8_t *first_packet,
                   int first_packet_size);

int av3a_core_decode_frame(AV3ACoreDecoder *dec,
                           const uint8_t *packet,
                           int packet_size,
                           int16_t *pcm,
                           int pcm_capacity_samples,
                           int *nb_samples,
                           int *channels,
                           int *sample_rate);

void av3a_core_close(AV3ACoreDecoder **dec);
```

Then the FFmpeg decoder wrapper should:

- expose `AV_CODEC_ID_AVS3_AUDIO`
- allocate decoder private context
- parse header/extradata into the AVS3A state
- output `AV_SAMPLE_FMT_S16` first
- set `frame->nb_samples` to the AVS3 frame length, normally 1024
- set channel layout through modern FFmpeg `AVChannelLayout`
- return FFmpeg errors instead of terminating the process

The `arcav3adec` wrapper already handles most of this shape, but it still needs cleanup before shipping:

- remove stale debug/file-output comments
- return stable FFmpeg error codes instead of converting many failures to `EAGAIN`
- validate `av_malloc` / `av_realloc` failure paths
- avoid decoder resets that silently discard useful error context
- keep channel layout handling explicit for object/HOA cases
- confirm whether the codec ID should remain `AV_CODEC_ID_AV3A` or be mapped from the older local name `AV_CODEC_ID_AVS3_AUDIO`

## Library hardening

The build patch turns the decoder subtree into a static library, removes the
CLI `main()` and file/WAV I/O objects, and silences reference-decoder console
logging in library mode. The packet-buffer API and embedded model are already
present in the pinned source.

The upstream decoder still contains `exit(...)` in exceptional allocation and
invalid-internal-configuration paths. Normal decode errors return through the
four-function API, but a later hardening pass should convert all remaining
fatal paths into decoder error returns before treating untrusted AV3A input as
fully isolated. This is a decoder-core risk, not an SDL/AO issue.

## FFmpeg forward-port risks

The local FFmpeg patch targets FFmpeg 4.4.2. The current mpv workflow builds a much newer FFmpeg snapshot, so direct file replacement is not expected to compile.

Known API migration areas:

- `AVInputFormat` / `AVOutputFormat` registration layout has changed in newer FFmpeg internals.
- old `codecpar->channels` / `channel_layout` usage must move to `AVChannelLayout`.
- parser and codec declarations need modern names and registration style.
- adding a new codec ID requires checking the current `codec_id.h` location and avoiding conflicts.
- MP4/MPEG-TS integration must be forward-ported as targeted hunks, not by replacing full files.

## Stage split

Stage 1: basic playback

- AV3A stream is detected in raw `.av3a`, TS, and MP4 where the old patch supports it.
- mpv sees an audio track instead of an unknown stream.
- FFmpeg decodes to PCM.
- stereo / normal channel-based content is the primary acceptance target.
- object and HOA content may initially expose decoded transport channels or return a clear unsupported-profile error.

Stage 2: spatial rendering

- add binaural or speaker renderer from the renderer reference sources
- preserve object count, HOA order, and metadata in the decoder private context
- add a renderer mode such as `off/basic`, `binaural`, or `speaker`
- rebuild the kernel with renderer support

If Stage 1 keeps profile metadata and uses a real FFmpeg decoder wrapper, Stage 2 is an incremental rebuild, not a full kernel rewrite.

## CI integration requirement

This requirement is now implemented with pinned public sources:

- `Sourcecodeforplayer` at `e7d244d29454eb04c968cd98a30587303a9c15f8`
- `llawsxx/FFmpeg` at `18c01ad424ca7712ef9a9d46953308efc75c4776`

CI builds and installs `libAVS3AudioDec.a` with the same MinGW toolchain and
prefix used by FFmpeg, enables `--enable-libarcdav3a`, verifies the four static
library symbols, checks `CONFIG_LIBARCDAV3A_DECODER`, and checks that the final
`mpv.exe` contains the decoder registration string.

GitHub Actions cannot see `C:\Users\杳知\Desktop\AudioVivid源码`. The build must either:

- add a reproducible source snapshot under the repository, or
- clone/download the public source during the workflow, pinned to a commit or archive hash.

For a stable public package, pinning is required. Do not depend on an unpinned branch tip.

With `arcav3adec`, CI additionally needs:

- a pinned source for `AVS3AudioDec`
- a cross-compile step that installs `libAVS3AudioDec.a` and headers into the same MinGW prefix used by FFmpeg
- FFmpeg configure args including `--enable-libarcdav3a`
- an assertion that `ffmpeg -decoders` or mpv's linked FFmpeg exposes `libarcdav3a`

The selected `Sourcecodeforplayer/av3adecoder` tree already exports the exact
four functions expected by `avs3_decoder_interface.h`; the local patch only
turns it into a reproducible static-library target and removes CLI-only code.

## Acceptance tests

Minimum verification for Stage 1:

- `ffmpeg -hide_banner -i sample.av3a` reports `Audio: avs3_audio` or equivalent AV3A codec name.
- `ffmpeg -i sample.av3a -f wav out.wav` produces valid PCM WAV.
- `mpv.com --no-config sample.av3a --ao=pcm --ao-pcm-file=out.wav` exits successfully.
- sample inside MPEG-TS is detected through stream type `0xd5`.
- legacy/test MPEG-TS that incorrectly labels AV3A as stream type `0x04` is
  reclassified only after three consecutive AV3A headers match computed frame
  boundaries; the codec parser must then reassemble exact AV3A frames across
  arbitrary PES boundaries, and ordinary MPEG audio must remain MPEG audio.
- sample inside MP4 is detected through `av3a`.
- ordinary AAC/AC3/EAC3/TrueHD/DTS playback is unchanged.
- existing HDR/image-subtitle mpv patch still applies and `mpv.com --no-config --list-options` still exposes the expected custom options.

## Current implementation status

- Reproducible library and FFmpeg integration patches are implemented under
  `build/av3a`.
- The GitHub Actions mpv build graph includes the pinned decoder before FFmpeg.
- The decoder library has been cross-compiled for Windows x64 and linked through
  a four-symbol smoke program locally.
- GitHub Actions Run `30600707954` completed successfully from commit
  `520f7b4b90d2382daa8f27354539589788161ddf`; the accepted Windows kernel is
  `mpv v0.41.0-847-gb766af840`.
- Full MP4, raw `.av3a`, standard `0xd5` TS, and legacy `0x04` mistagged TS
  decoding passed. The mistagged TS produced all 153 frames / 156672 samples,
  completed mpv playback, and passed stereo Realtek WASAPI output.
- Runtime AV3A -> AAC -> AV3A track switching, 60-second seek, ordinary
  AAC/MP3/FLAC regression, full portable configuration loading, Schannel, and
  the existing HDR image-subtitle options were retained.
- `mpv-changerefresh` remains intentionally deferred. SDL AO is not required for
  Stage 1 and WASAPI remains the Windows default. Full object/HOA spatial
  rendering remains Stage 2.
