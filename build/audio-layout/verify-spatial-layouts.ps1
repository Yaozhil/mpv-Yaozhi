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
        for ($n = 0; $n -lt $sampleCount; $n++) {
            $offset = (($start + $n) * $ChannelCount + $channel) * 4
            $samples[$n] = [BitConverter]::ToInt32($bytes, $offset)
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
        if ($magnitudes[$best] -lt ($magnitudes[$second] * 1.5)) {
            throw "$Label channel $channel probe separation is too weak"
        }
    }
}

$sampleRate = 48000
$duration = 0.35
$cases = @(
    @{
        Name = "5.1.4"
        Count = 10
        FFmpegLayout = "FL+FR+FC+LFE+SL+SR+TFL+TFR+TBL+TBR"
        MpvLayout = "fl-fr-fc-lfe-sl-sr-tfl-tfr-tbl-tbr"
    },
    @{
        Name = "7.1.4"
        Count = 12
        FFmpegLayout = "FL+FR+FC+LFE+BL+BR+SL+SR+TFL+TFR+TBL+TBR"
        MpvLayout = "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr"
    },
    @{
        Name = "9.1.4"
        Count = 14
        FFmpegLayout = "FL+FR+FC+LFE+BL+BR+SL+SR+TFL+TFR+TBL+TBR+TSL+TSR"
        MpvLayout = "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr-tsl-tsr"
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
                "--audio-channels=$($case.MpvLayout)",
                "--msg-level=all=warn,swresample=trace", $source
            )
        Assert-ExactPcm -Label "$name $extension" `
            -ExpectedPath $referencePath -ActualPath $mpvOutputPath
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

$customName = "9.1.6-custom"
$customCount = 16
$customLayout =
    "fl-fr-fc-lfe-bl-br-sl-sr-tfl-tfr-tbl-tbr-tsl-tsr-wl-wr"
$customFrequencies = New-Object double[] $customCount
for ($channel = 0; $channel -lt $customCount; $channel++) {
    $customFrequencies[$channel] = 220.0 + 97.0 * $channel
}
$customInput = Join-Path $WorkDir "$customName-input.s16"
$customOutput = Join-Path $WorkDir "$customName-mpv.s32"
$customLog = Join-Path $WorkDir "$customName-mpv.log"
Remove-Item -LiteralPath $customInput, $customOutput, $customLog `
    -Force -ErrorAction SilentlyContinue
Write-S16Probe -Path $customInput -ChannelCount $customCount `
    -Frequencies $customFrequencies -SampleRate $sampleRate `
    -Duration $duration
Invoke-Checked -Label "$customName raw PCM conversion" `
    -Exe $MpvPath -LogPath $customLog -Arguments @(
        "--no-config", "--audio-display=no", "--vo=null",
        "--demuxer=rawaudio", "--demuxer-rawaudio-format=s16le",
        "--demuxer-rawaudio-channels=$customLayout",
        "--demuxer-rawaudio-rate=$sampleRate",
        "--ao=pcm", "--ao-pcm-waveheader=no",
        "--ao-pcm-file=$customOutput", "--audio-format=s32",
        "--audio-channels=$customLayout",
        "--msg-level=all=warn,swresample=trace", $customInput
    )
Assert-ChannelFrequencies -Label $customName -Path $customOutput `
    -ChannelCount $customCount -Frequencies $customFrequencies `
    -SampleRate $sampleRate
Write-Host "$customName explicit custom-order validation passed"
