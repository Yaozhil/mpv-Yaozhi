# AVS3A content selection

The existing decoder renders every decoded object by default. DVB No3 instead
defines four programme contents, each referencing the shared 7.1.4 bed and two
additional objects. A content selector must follow those references; four object
channels alone do not identify four presets.

Three independent layers preserve the pinned SDK/FFmpeg versions and previous
VC1, script API and Windows fixes:

- `avs3-audiodecoder-preselections.patch` adds a separate bounded metadata ABI.
  It resolves programme/content/object/pack references to transport PCM masks.
  Unsupported complementary groups, ambiguous shared PCM, non-identity channel
  mappings and non-object formats are not advertised as selectable.
- `ffmpeg-libarcdav3a-preselections.patch` adds `av3a_content=-1` (the unchanged
  all-object default) or an encoded content ID. In binaural mode the mask gates
  the existing final per-source gain for each block; gain, mute and positions
  otherwise retain their metadata semantics. Native PCM is unchanged. After a
  seek, missing static metadata temporarily silences a selected content while
  waiting at most 64 decoded blocks. Invalid or unknown selections fail closed.
  Each output packet retains its matching graph even if a subsequent header
  recreates the underlying decoder.
- `0060-av3a-content-selection.patch` exposes the decoder's read-only bounded
  `av3a_contents` JSON as `audio-av3a-content-info` under the existing decoder
  thread lock. It does not aggregate ambiguous stream groups or parse logs.

The local player menu uses only this property and confirms `applied=true` before
marking a particular content active. It preserves manual native mode and other
file-local AVOptions. Changing a content rebuilds the audio chain and can briefly
interrupt playback; gapless switching is not claimed.

The independently parsed No3 sample has programme IDs 0,1,2,3 and masks
`0x3fff`, `0x5fff`, `0x6fff`, `0x9fff`. It provides object labels AO_O1 through
AO_O4, without instrument names or an explicit default. None of these sample
masks or labels is hardcoded in the implementation.

`source-lock.json.av3a_preselections` binds all three patches, complete mpv
variant trees, the full historical SDK/FFmpeg patch chains and actual C contract
sources. Historical VC1/HOLD/EOF/PTS gates still inspect their original layers.
The graph, per-block routing, output-graph ownership and property contracts run
with the native CI compiler. These contracts do not replace full binary playback,
PCM comparison, seek, pause and prior-core regression checks before installation.
