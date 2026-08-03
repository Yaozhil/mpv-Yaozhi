param(
    [Parameter(Mandatory = $true)]
    [string]$FFmpegPath,

    [Parameter(Mandatory = $true)]
    [string]$MpvPath,

    [string]$WorkDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $WorkDir) {
    $WorkDir = Join-Path $env:TEMP "mpv-spatial-layout-validation"
}
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

function Invoke-Checked {
    param(
        [string]$Label,
        [string]$Exe,
        [string[]]$Arguments,
        [string]$LogPath = ""
    )

    $output = & $Exe @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($LogPath) {
        if ($null -eq $output) {
            [IO.File]::WriteAllText($LogPath, "")
        } else {
            [IO.File]::WriteAllLines(
                $LogPath,
                [string[]]($output | ForEach-Object { "$_" })
            )
        }
    }
    if ($exitCode -ne 0) {
        $text = ($output | ForEach-Object { "$_" }) -join "`n"
        throw "$Label failed with exit code $exitCode`n$text"
    }
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

function Write-S16Probe {
    param(
        [string]$Path,
        [int]$ChannelCount,
        [double[]]$Frequencies,
        [int]$SampleRate,
        [double]$Duration
    )

    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Create,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    $writer = New-Object IO.BinaryWriter $stream
    try {
        $frameCount = [int]($SampleRate * $Duration)
        for ($frame = 0; $frame -lt $frameCount; $frame++) {
            $time = $frame / [double]$SampleRate
            for ($channel = 0; $channel -lt $ChannelCount; $channel++) {
                $value = [int][Math]::Round(
                    0.15 * [int16]::MaxValue *
                    [Math]::Sin(2.0 * [Math]::PI *
                        $Frequencies[$channel] * $time)
                )
                $writer.Write([int16]$value)
            }
        }
    } finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

function Assert-ExactPcm {
    param(
        [string]$Label,
        [string]$ExpectedPath,
        [string]$ActualPath
    )

    $expected = Get-Item -LiteralPath $ExpectedPath
    $actual = Get-Item -LiteralPath $ActualPath
    if ($expected.Length -ne $actual.Length) {
        throw "$Label PCM length mismatch: $($expected.Length) != $($actual.Length)"
    }

    $expectedHash = Get-Sha256 -Path $ExpectedPath
    $actualHash = Get-Sha256 -Path $ActualPath
    if ($expectedHash -ne $actualHash) {
        throw "$Label PCM hash mismatch: $expectedHash != $actualHash"
    }
}

function Assert-S16ToS32Exact {
    param(
        [string]$Label,
        [string]$InputPath,
        [string]$OutputPath,
        [int]$ChannelCount
    )

    $input = [IO.File]::ReadAllBytes($InputPath)
    $output = [IO.File]::ReadAllBytes($OutputPath)
    if (($input.Length % (2 * $ChannelCount)) -ne 0) {
        throw "$Label input is not valid interleaved s16 PCM"
    }
    if ($output.Length -ne ($input.Length * 2)) {
        throw "$Label PCM length mismatch: $($output.Length) != $($input.Length * 2)"
    }

    $sampleCount = [int]($input.Length / 2)
    for ($sample = 0; $sample -lt $sampleCount; $sample++) {
        $expected = [int32](
            [int64][BitConverter]::ToInt16($input, $sample * 2) * 65536
        )
        $actual = [BitConverter]::ToInt32($output, $sample * 4)
        if ($actual -ne $expected) {
            $frame = [int]($sample / $ChannelCount)
            $channel = $sample % $ChannelCount
            throw "$Label sample mismatch at frame $frame channel $channel"
        }
    }
}

function Assert-ChannelFrequencies {
    param(
        [string]$Label,
        [string]$Path,
        [int]$ChannelCount,
        [double[]]$Frequencies,
        [int]$SampleRate
    )

    $bytes = [IO.File]::ReadAllBytes($Path)
    $frameSize = 4 * $ChannelCount
    if ($bytes.Length -eq 0 -or ($bytes.Length % $frameSize) -ne 0) {
        throw "$Label is not valid interleaved s32 PCM"
    }

    $frameCount = [int]($bytes.Length / $frameSize)
    $start = [Math]::Min(2048, [Math]::Max(0, $frameCount - 4096))
    $sampleCount = [Math]::Min(4096, $frameCount - $start)
    if ($sampleCount -lt 2048) {
        throw "$Label is too short for channel-frequency validation"
    }

    for ($channel = 0; $channel -lt $ChannelCount; $channel++) {
        $samples = New-Object double[] $sampleCount
        $sumSquares = 0.0
        for ($n = 0; $n -lt $sampleCount; $n++) {
            $offset = (($start + $n) * $ChannelCount + $channel) * 4
            $samples[$n] = [BitConverter]::ToInt32($bytes, $offset)
            $sumSquares += $samples[$n] * $samples[$n]
        }
        $rms = [Math]::Sqrt($sumSquares / $sampleCount)
        if ($rms -lt 1000000.0) {
            throw "$Label channel $channel is silent or too weak"
        }

        $magnitudes = New-Object double[] $Frequencies.Count
        for ($candidate = 0; $candidate -lt $Frequencies.Count; $candidate++) {
            $omega = 2.0 * [Math]::PI * $Frequencies[$candidate] / $SampleRate
            $sumCos = 0.0
            $sumSin = 0.0
            for ($n = 0; $n -lt $sampleCount; $n++) {
                $angle = $omega * $n
                $sumCos += $samples[$n] * [Math]::Cos($angle)
                $sumSin += $samples[$n] * [Math]::Sin($angle)
            }
            $magnitudes[$candidate] =
                [Math]::Sqrt($sumCos * $sumCos + $sumSin * $sumSin)
        }

        $ranked = 0..($Frequencies.Count - 1) |
            Sort-Object { $magnitudes[$_] } -Descending
        $best = [int]$ranked[0]
        $second = [int]$ranked[1]
        if ($best -ne $channel) {
            throw "$Label channel $channel contains probe $best instead of $channel"
        }
        if ($magnitudes[$best] -lt ($magnitudes[$second] * 3.0)) {
            throw "$Label channel $channel probe separation is too weak"
        }
    }
}

function Test-RawLayoutConversion {
    param(
        [string]$Name,
        [string]$Layout,
        [int]$ChannelCount,
        [double[]]$Frequencies,
        [int]$SampleRate,
        [double]$Duration,
        [string]$WorkDir,
        [string]$MpvPath
    )

    $input = Join-Path $WorkDir "$Name-input.s16"
    $output = Join-Path $WorkDir "$Name-mpv.s32"
    $log = Join-Path $WorkDir "$Name-mpv.log"
    Remove-Item -LiteralPath $input, $output, $log `
        -Force -ErrorAction SilentlyContinue

    Write-S16Probe -Path $input -ChannelCount $ChannelCount `
        -Frequencies $Frequencies -SampleRate $SampleRate `
        -Duration $Duration
    $durationText = $Duration.ToString(
        [Globalization.CultureInfo]::InvariantCulture
    )
    Invoke-Checked -Label "$Name raw PCM conversion" `
        -Exe $MpvPath -LogPath $log -Arguments @(
            "--no-config", "--audio-display=no", "--vo=null",
            "--demuxer=rawaudio", "--demuxer-rawaudio-format=s16le",
            "--demuxer-rawaudio-channels=$Layout",
            "--demuxer-rawaudio-rate=$SampleRate",
            "--ao=pcm", "--ao-pcm-waveheader=no",
            "--ao-pcm-file=$output", "--audio-format=s32",
            "--audio-channels=$Layout", "--length=$durationText",
            "--msg-level=all=warn,swresample=trace", $input
        )
    Assert-S16ToS32Exact -Label $Name -InputPath $input `
        -OutputPath $output -ChannelCount $ChannelCount
    Write-Host "$Name exact positional conversion passed"
}

$sampleRate = 48000
$duration = 0.35
$cases = @(
    @{
        Name = "5.1.4"
        Count = 10
        FFmpegLayout = "FL+FR+FC+LFE+SL+SR+TFL+TFR+TBL+TBR"
        MpvLayout = "fl-fr-fc-lfe-sl-sr-tfl-tfr-tbl-tbr"
        WavPackLayout = "fl-fr-fc-lfe-sl-sr-tfl-tfr-tbl-tbr"
    },
    @{
        Name = "7.1.4"
        Count = 12
        FFmpegLayout = "FL+FR+FC+LFE+BL+BR+SL+SR+TFL+TFR+TBL+TBR"
        MpvLayout = "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr"
        WavPackLayout = "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr"
    },
    @{
        Name = "9.1.4"
        Count = 14
        FFmpegLayout = "FL+FR+FC+LFE+BL+BR+SL+SR+TFL+TFR+TBL+TBR+TSL+TSR"
        MpvLayout = "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr-tsl-tsr"
        # WavPack v4 cannot carry TSL/TSR speaker IDs. FFmpeg therefore reads
        # this 14-channel file using its mask-compatible 9.1.4 alias.
        WavPackLayout =
            "fl-fr-fc-lfe-bl-br-flc-frc-sl-sr-tfl-tfr-tbl-tbr"
    },
    @{
        Name = "9.1.6"
        Count = 16
        # Native FFmpeg/WAVE bit order places WL/WR before TSL/TSR. The
        # conceptual 9.1.6 reference remains label-based, not index-based.
        FFmpegLayout =
            "FL+FR+FC+LFE+BL+BR+SL+SR+TFL+TFR+TBL+TBR+WL+WR+TSL+TSR"
        MpvLayout =
            "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr-wl-wr-tsl-tsr"
        # The generated WavPack stream has no assignable 16-channel speaker
        # mask, so FFmpeg applies its own 9.1.6 default on decode.
        WavPackLayout =
            "fl-fr-fc-lfe-bl-br-flc-frc-sl-sr-tfl-tfr-tbl-tbr-tsl-tsr"
    }
)

foreach ($case in $cases) {
    $name = [string]$case.Name
    $channelCount = [int]$case.Count
    $frequencies = New-Object double[] $channelCount
    $expressions = New-Object string[] $channelCount
    for ($channel = 0; $channel -lt $channelCount; $channel++) {
        $frequencies[$channel] = 220.0 + 97.0 * $channel
        $expressions[$channel] =
            "0.04*sin(2*PI*$($frequencies[$channel])*t)"
    }

    $prefix = Join-Path $WorkDir ($name -replace "\.", "-")
    $wavPath = "$prefix.wav"
    $wvPath = "$prefix.wv"
    $opusPath = "$prefix.opus"
    $sourceFilter = "aevalsrc=exprs=$(($expressions -join '|'))" +
        ":s=${sampleRate}:d=${duration}:c=$($case.FFmpegLayout)"

    Invoke-Checked -Label "$name WAV generation" -Exe $FFmpegPath -Arguments @(
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", $sourceFilter,
        "-c:a", "pcm_s32le", $wavPath
    )
    Invoke-Checked -Label "$name WavPack generation" -Exe $FFmpegPath -Arguments @(
        "-hide_banner", "-loglevel", "error", "-y",
        "-i", $wavPath, "-c:a", "wavpack", $wvPath
    )

    foreach ($source in @($wavPath, $wvPath)) {
        $extension = [IO.Path]::GetExtension($source).TrimStart(".")
        $outputLayout = [string]$case.MpvLayout
        if ($extension -eq "wv") {
            $outputLayout = [string]$case.WavPackLayout
        }
        $referencePath = "$prefix-$extension-reference.s32"
        $mpvOutputPath = "$prefix-$extension-mpv.s32"
        $mpvLog = "$prefix-$extension-mpv.log"
        Remove-Item -LiteralPath $referencePath, $mpvOutputPath, $mpvLog `
            -Force -ErrorAction SilentlyContinue

        Invoke-Checked -Label "$name $extension FFmpeg decode" `
            -Exe $FFmpegPath -Arguments @(
                "-hide_banner", "-loglevel", "error", "-y",
                "-i", $source, "-map", "0:a:0",
                "-c:a", "pcm_s32le", "-f", "s32le", $referencePath
            )
        Invoke-Checked -Label "$name $extension mpv decode" `
            -Exe $MpvPath -LogPath $mpvLog -Arguments @(
                "--no-config", "--audio-display=no", "--vo=null",
                "--ao=pcm", "--ao-pcm-waveheader=no",
                "--ao-pcm-file=$mpvOutputPath", "--audio-format=s32",
                "--audio-channels=$outputLayout",
                "--msg-level=all=warn,swresample=trace", $source
            )
        Assert-ExactPcm -Label "$name $extension" `
            -ExpectedPath $referencePath -ActualPath $mpvOutputPath
        Assert-ChannelFrequencies -Label "$name $extension" `
            -Path $mpvOutputPath -ChannelCount $channelCount `
            -Frequencies $frequencies -SampleRate $sampleRate
    }

    # Opus mapping family 255 carries channel positions only. Validate it only
    # with the explicit label order supplied to mpv; never infer speaker
    # semantics from the channel count.
    Invoke-Checked -Label "$name Opus generation" -Exe $FFmpegPath -Arguments @(
        "-hide_banner", "-loglevel", "error", "-y",
        "-i", $wavPath, "-c:a", "libopus", "-mapping_family", "255",
        "-application", "audio", "-b:a", "768k", $opusPath
    )
    $opusPcm = "$prefix-opus-mpv.s32"
    $opusLog = "$prefix-opus-mpv.log"
    Remove-Item -LiteralPath $opusPcm, $opusLog `
        -Force -ErrorAction SilentlyContinue
    Invoke-Checked -Label "$name Opus mpv decode" `
        -Exe $MpvPath -LogPath $opusLog -Arguments @(
            "--no-config", "--audio-display=no", "--vo=null",
            "--ao=pcm", "--ao-pcm-waveheader=no",
            "--ao-pcm-file=$opusPcm", "--audio-format=s32",
            "--audio-channels=$($case.MpvLayout)",
            "--msg-level=all=warn,swresample=trace", $opusPath
        )
    Assert-ChannelFrequencies -Label "$name Opus" -Path $opusPcm `
        -ChannelCount $channelCount -Frequencies $frequencies `
        -SampleRate $sampleRate

    Write-Host "$name WAV/WavPack/Opus channel-order validation passed"
}

foreach ($case in $cases) {
    $channelCount = [int]$case.Count
    $frequencies = New-Object double[] $channelCount
    for ($channel = 0; $channel -lt $channelCount; $channel++) {
        $frequencies[$channel] = 220.0 + 97.0 * $channel
    }
    Test-RawLayoutConversion `
        -Name "$(($case.Name -replace '\.', '-'))-canonical" `
        -Layout ([string]$case.MpvLayout) `
        -ChannelCount $channelCount -Frequencies $frequencies `
        -SampleRate $sampleRate -Duration $duration `
        -WorkDir $WorkDir -MpvPath $MpvPath
}

$rawCases = @(
    @{
        Name = "9-1-6-custom"
        Layout =
            "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr-tsl-tsr-wl-wr"
        Count = 16
    },
    @{
        Name = "top-front-custom"
        Layout = "tfr-tfl"
        Count = 2
    },
    @{
        Name = "side-custom"
        Layout = "sr-sl"
        Count = 2
    },
    @{
        Name = "unknown4"
        Layout = "unknown4"
        Count = 4
    },
    @{
        Name = "front-na"
        Layout = "fl-fr-na"
        Count = 3
    }
)
foreach ($rawCase in $rawCases) {
    $channelCount = [int]$rawCase.Count
    $frequencies = New-Object double[] $channelCount
    for ($channel = 0; $channel -lt $channelCount; $channel++) {
        $frequencies[$channel] = 401.0 + 211.0 * $channel
    }
    Test-RawLayoutConversion `
        -Name ([string]$rawCase.Name) -Layout ([string]$rawCase.Layout) `
        -ChannelCount $channelCount -Frequencies $frequencies `
        -SampleRate $sampleRate -Duration $duration `
        -WorkDir $WorkDir -MpvPath $MpvPath
}
