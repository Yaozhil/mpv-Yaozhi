from pathlib import Path
import sys


SOURCE_FILES = (
    "av3adecoder/avs3Decoder/include/avs3_decoder_interface.h",
    "av3adecoder/avs3Decoder/src/avs3_init_dec.c",
    "av3adecoder/avs3Decoder/src/decoder.c",
    "av3a_binaural_render/AudioDecoder/av3a_binaural_render/avs3_audio.cpp",
    "av3a_binaural_render/AudioDecoder/av3a_binaural_render/avs3_audio.h",
    "av3a_binaural_render/AudioDecoder/av3a_binaural_render/avs3_audio_types.h",
    (
        "av3a_binaural_render/AudioDecoder/av3a_binaural_render/"
        "core/ambisonic_rotator.cpp"
    ),
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: normalize-source-eol.py SOURCE_DIR")

    source_dir = Path(sys.argv[1])
    for relative_path in SOURCE_FILES:
        source_path = source_dir / relative_path
        if not source_path.is_file():
            raise SystemExit(f"missing AV3A source file: {source_path}")

        content = source_path.read_bytes()
        source_path.write_bytes(content.replace(b"\r\n", b"\n"))


if __name__ == "__main__":
    main()
