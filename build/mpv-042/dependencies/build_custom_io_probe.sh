#!/usr/bin/env bash
# Usage: bash build_custom_io_probe.sh <winbuild-root> <output.exe>
# Run after the exact FFmpeg candidate is installed. Execute the produced PE
# on Windows; compilation alone does not count as a runtime PASS.
set -euo pipefail
winbuild=$(realpath "$1")
output=$(realpath -m "$2")
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$(dirname "$output")"
prefix="$winbuild/build64/install/x86_64-w64-mingw32"
cc="$winbuild/build64/install/bin/cross-gcc"
if [ ! -x "$cc" ]; then
  cc="$winbuild/build64/install/bin/x86_64-w64-mingw32-gcc"
fi
test -x "$cc"
test -f "$prefix/lib/libavformat.a"
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
export PKG_CONFIG_PATH="$PKG_CONFIG_LIBDIR"
export PKG_CONFIG_SYSROOT_DIR=
# pkg-config emits compiler switches; intentional shell splitting preserves
# this fixed local toolchain's conventional space-free CI workspace paths.
# shellcheck disable=SC2046
"$cc" -O2 -Wall -Wextra "$source_dir/test_custom_io_cleanup.c" -o "$output" \
  $(pkg-config --static --cflags --libs libavformat libavcodec libavutil) -lstdc++
sha256sum "$output"
"$cc" --version > "$output.compiler-version.txt"
python3 - "$cc" "$output" "$source_dir/test_custom_io_cleanup.c" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
def record(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
cc, output, source = sys.argv[1:]
result = {'status': 'PASS_PROBE_COMPILED_NOT_RUN', 'compiler': record(cc),
          'version': Path(output + '.compiler-version.txt').read_text(),
          'source': record(source), 'binary': record(output)}
Path(output + '.build.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
PY
