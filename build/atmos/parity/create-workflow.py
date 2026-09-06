"""Derive a two-variant candidate workflow without dropping main build checks."""
import argparse
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--main-workflow',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[3]
text=args.main_workflow.read_text(encoding='utf-8')
start=text.index('permissions:')
text='''name: "Build V1.0.0 main and Atmos parity candidates"

on:
  workflow_dispatch:
  push:
    branches: [codex/v100-core-parity-20260907]
    paths:
      - .github/workflows/build-mpv-v100-parity.yml
      - build/atmos/**
      - build/bluray-menu/patches/**

concurrency:
  group: v100-parity-${{ github.ref }}
  cancel-in-progress: true

'''+text[start:]
text=text.replace('  build:\n    runs-on:', '''  build:
    strategy:
      fail-fast: false
      matrix:
        variant: [main, atmos]
    runs-on:''',1)
text=text.replace('build/core-migration/luna-mpv-c318236.patch','build/atmos/parity/main-core.patch')
text=text.replace('name: mpv-bluray-menu-smtc-c318236-x86_64','name: mpv-v100-${{ matrix.variant }}-x86_64')
text=text.replace('name: mpv-hdr-pgs-build-logs','name: mpv-v100-${{ matrix.variant }}-build-logs')
text=text.replace("hashFiles('.github/workflows/build-mpv-hdr-pgs.yml',", "hashFiles('.github/workflows/build-mpv-v100-parity.yml', 'build/atmos/**', 'build/bluray-menu/**',")
text=text.replace('key: mpv-hdr-pgs-av3a-schannel-v1-ubuntu-gcc64-', 'key: mpv-v100-${{ matrix.variant }}-ubuntu-gcc64-',1)
anchor='      - name: Restore reusable build cache\n'
assert text.count(anchor)==1
prepare='''      - name: Check out pinned ASIO headers
        if: matrix.variant == 'atmos'
        uses: actions/checkout@v6
        with:
          repository: audiosdk/asio
          ref: 496a0765b8bb9c26f764f22f9a9712a937177db2
          path: third-party/asio

      - name: Preserve common features and prepare variant
        shell: bash
        run: |
          set -euxo pipefail
          python3 build/atmos/parity/prepare-winbuild.py \\
            --winbuild winbuild/mpv-winbuild-cmake \\
            --variant '${{ matrix.variant }}' \\
            --asio-sdk "$GITHUB_WORKSPACE/third-party/asio"

'''
text=text.replace(anchor,prepare+anchor,1)
text=text.replace('  validate-windows:\n    needs: build\n', '''  validate-windows:
    needs: [build, build-orender]
    strategy:
      fail-fast: false
      matrix:
        variant: [main, atmos]
''',1)
anchor='      - name: Verify spatial audio and AV3A playback on Windows\n'
assert text.count(anchor)==1
text=text.replace(anchor,'''      - name: Download matching renderer
        if: matrix.variant == 'atmos'
        uses: actions/download-artifact@v6
        with:
          name: orender-v0.5.2-windows-x86_64
          path: renderer

'''+anchor,1)
anchor='          $enabledFeatures = @(\n'
assert text.count(anchor)==1
text=text.replace(anchor,'''          if ('${{ matrix.variant }}' -eq 'atmos') {
            $requiredFeatures += @('orender','asio')
            if ($optionText -notmatch 'ad-orender-library' -or $aoText -notmatch 'Steinberg ASIO') {
              throw 'Atmos decoder/ASIO interface missing'
            }
          }
'''+anchor,1)
# Bundled renderer and its license remain in a separate artifact. Installation
# is a later local step, after real bridge/menu/audio verification.
text+='''
  build-orender:
    runs-on: windows-latest
    timeout-minutes: 60
    steps:
      - name: Check out pinned renderer
        uses: actions/checkout@v6
        with:
          repository: mgth/Omniphony
          ref: f9a79721af64ad9c39042d4deded158b568fc598
      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
      - name: Build renderer
        working-directory: omniphony-renderer
        run: cargo build --locked --profile release-deploy -p orender_ffi
      - name: Package renderer
        shell: pwsh
        run: |
          New-Item -ItemType Directory -Force -Path out | Out-Null
          Copy-Item -LiteralPath omniphony-renderer/target/release-deploy/orender.dll -Destination out/
          Copy-Item -LiteralPath omniphony-renderer/orender_ffi/include/orender.h -Destination out/
          Get-ChildItem -File -Filter 'LICENSE*' | Copy-Item -Destination out/
          Get-ChildItem -LiteralPath out -File | Get-FileHash -Algorithm SHA256 |
            Select-Object Hash,Path | ConvertTo-Json | Set-Content out/SHA256.json
      - name: Upload renderer
        uses: actions/upload-artifact@v6
        with:
          name: orender-v0.5.2-windows-x86_64
          path: out/*
          if-no-files-found: error
          retention-days: 7
'''
path=root/'.github/workflows/build-mpv-v100-parity.yml'
path.write_text(text,encoding='utf-8',newline='\n')
assert "workflow_dispatch:" in text and 'branches: [codex/v100-core-parity-20260907]' in text
assert "'vapoursynth'" in text and "'win32-smtc'" in text and 'verify-fel.ps1' in text
assert text.count('variant: [main, atmos]')==2
print('PARITY_WORKFLOW_PREPARED push_scoped_to_candidate_branch=true')
