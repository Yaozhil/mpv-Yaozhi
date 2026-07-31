param(
    [Parameter(Mandatory = $true)]
    [string]$FFmpegPath,

    [string]$MpvPath,

    [string]$SamplePath = (Join-Path $PSScriptRoot "hoa-order1-128k.av3a"),

    [string]$ObjectSamplePath = (Join-Path $PSScriptRoot "bed-object-moving.av3a"),

    [string]$MetadataProbePath
)

$ErrorActionPreference = "Stop"
$work = Join-Path $env:TEMP ("av3a-stage2-" + [guid]::NewGuid().ToString("N"))

function Invoke-Checked {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )

    # Windows PowerShell 5.1 wraps native stderr lines as error records. With
    # ErrorActionPreference=Stop, normal FFmpeg diagnostics would terminate the
    # verifier before the native exit code can be checked.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $Executable @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $output = @($output | ForEach-Object { "$_" })
    if ($exitCode -ne 0) {
        throw "$Executable failed with exit code $exitCode`n$($output -join "`n")"
    }
    return $output
}

function Assert-Size {
    param(
        [string]$Path,
        [long]$Expected
    )

    $actual = (Get-Item -LiteralPath $Path).Length
    if ($actual -ne $Expected) {
        throw "Unexpected output size for $Path`: expected $Expected, got $actual"
    }
}

function Assert-Contains {
    param(
        [string[]]$Output,
        [string]$Pattern,
        [string]$Description
    )

    $text = ($Output | ForEach-Object { "$_" }) -join "`n"
    if ($text -notmatch $Pattern) {
        throw "Missing $Description in command output`n$text"
    }
}

function Assert-NotContains {
    param(
        [string[]]$Output,
        [string]$Pattern,
        [string]$Description
    )

    $text = ($Output | ForEach-Object { "$_" }) -join "`n"
    if ($text -match $Pattern) {
        throw "Unexpected $Description in command output`n$text"
    }
}

function Assert-SameHash {
    param(
        [string]$ExpectedPath,
        [string]$ActualPath
    )

    $expected = (Get-FileHash -Algorithm SHA256 -LiteralPath $ExpectedPath).Hash
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $ActualPath).Hash
    if ($actual -ne $expected) {
        throw "PCM hash mismatch: expected $expected from $ExpectedPath, got $actual from $ActualPath"
    }
}

function Assert-DecodeFormat {
    param(
        [string]$InputPath,
        [string]$Mode,
        [string]$SampleFormat,
        [int]$Channels,
        [string]$ChannelLayoutPattern
    )

    $output = Invoke-Checked $FFmpegPath @(
        "-hide_banner", "-loglevel", "info",
        "-av3a_render", $Mode,
        "-i", $InputPath,
        "-map", "0:a:0",
        "-frames:a", "1",
        "-af", "ashowinfo",
        "-f", "null",
        "NUL"
    )
    $line = $output |
        ForEach-Object { "$_" } |
        Where-Object { $_ -match "ashowinfo.*\bn:0\b" } |
        Select-Object -First 1

    if (-not $line) {
        throw "No first-frame ashowinfo output for AV3A render mode $Mode"
    }
    foreach ($expectation in @(
        @{ Pattern = "\bfmt:$([regex]::Escape($SampleFormat))\b"; Name = "sample format $SampleFormat" },
        @{ Pattern = "\bchannels:$Channels\b"; Name = "$Channels channels" },
        @{ Pattern = $ChannelLayoutPattern; Name = "expected channel layout" },
        @{ Pattern = "\brate:48000\b"; Name = "48 kHz sample rate" },
        @{ Pattern = "\bnb_samples:1024\b"; Name = "1024 samples per frame" }
    )) {
        if ($line -notmatch $expectation.Pattern) {
            throw "Unexpected $Mode frame metadata; missing $($expectation.Name)`n$line"
        }
    }
}

function Assert-MetadataProbe {
    if (-not $MetadataProbePath) {
        throw "MetadataProbePath is required for moving-object validation"
    }

    $output = Invoke-Checked $MetadataProbePath @($ObjectSamplePath)
    Assert-Contains $output `
        "\bsummary frames=281 dynamic_frames=281 changed_frames=([1-9][0-9]*) transport_channel=2 first_x=-?[0-9.]+ last_x=-?[0-9.]+ object1_changes=([1-9][0-9]*)\b" `
        "281-frame changing object metadata summary"
}

function Assert-Sample {
    param(
        [string]$Name,
        [string]$InputPath,
        [int]$ExpectedFrames,
        [int]$NativeChannels,
        [string]$NativeLayoutPattern
    )

    $nativeBytes = [long]$ExpectedFrames * 1024 * $NativeChannels * 2
    $binauralBytes = [long]$ExpectedFrames * 1024 * 2 * 4
    $nativePcm = Join-Path $work "$Name-native-s16le.pcm"
    $binauralPcm = Join-Path $work "$Name-binaural-f32le.pcm"
    $mpvNativePcm = Join-Path $work "$Name-mpv-native-s16le.pcm"
    $mpvBinauralPcm = Join-Path $work "$Name-mpv-binaural-f32le.pcm"

    Assert-DecodeFormat $InputPath "native" "s16" $NativeChannels $NativeLayoutPattern
    Assert-DecodeFormat $InputPath "binaural" "flt" 2 "\bchlayout:stereo\b"

    Invoke-Checked $FFmpegPath @(
        "-hide_banner", "-loglevel", "warning", "-y",
        "-av3a_render", "native",
        "-i", $InputPath,
        "-map", "0:a:0",
        "-c:a", "pcm_s16le",
        "-f", "s16le",
        $nativePcm
    ) | Out-Null
    Assert-Size $nativePcm $nativeBytes

    Invoke-Checked $FFmpegPath @(
        "-hide_banner", "-loglevel", "warning", "-y",
        "-av3a_render", "binaural",
        "-i", $InputPath,
        "-map", "0:a:0",
        "-c:a", "pcm_f32le",
        "-f", "f32le",
        $binauralPcm
    ) | Out-Null
    Assert-Size $binauralPcm $binauralBytes

    if (-not $MpvPath) {
        return
    }

    $nativeMpvOutput = Invoke-Checked $MpvPath @(
        "--no-config",
        "--vo=null",
        "--ao=pcm",
        "--ao-pcm-waveheader=no",
        "--ao-pcm-file=$mpvNativePcm",
        "--audio-display=no",
        "--audio-format=s16",
        "--audio-samplerate=48000",
        "--ad-lavc-o=av3a_render=native",
        $InputPath
    )
    Assert-NotContains $nativeMpvOutput `
        "Converting libavcodec frame to mpv frame failed" `
        "libavcodec-to-mpv frame conversion failure"
    Assert-NotContains $nativeMpvOutput `
        "Audio filter chain:|libswresample|lavrresample" `
        "native audio conversion"
    Assert-Size $mpvNativePcm $nativeBytes
    Assert-SameHash $nativePcm $mpvNativePcm

    $binauralMpvOutput = Invoke-Checked $MpvPath @(
        "--no-config",
        "--vo=null",
        "--ao=pcm",
        "--ao-pcm-waveheader=no",
        "--ao-pcm-file=$mpvBinauralPcm",
        "--audio-display=no",
        "--audio-format=float",
        "--audio-samplerate=48000",
        "--audio-channels=stereo",
        "--ad-lavc-o=av3a_render=binaural",
        $InputPath
    )
    Assert-NotContains $binauralMpvOutput `
        "Cannot open Libavresample context|libswresample failed to initialize" `
        "binaural resampler initialization failure"
    Assert-Size $mpvBinauralPcm $binauralBytes
    Assert-SameHash $binauralPcm $mpvBinauralPcm
}

try {
    New-Item -ItemType Directory -Path $work | Out-Null

    $decoderHelp = Invoke-Checked $FFmpegPath @(
        "-hide_banner",
        "-h", "decoder=libarcdav3a"
    )
    Assert-Contains $decoderHelp "\bav3a_render\b" "av3a_render decoder option"
    Assert-Contains $decoderHelp "\(default native\)" "native decoder default"

    Assert-MetadataProbe
    Assert-Sample "hoa" $SamplePath 94 4 "\bchlayout:4 channels\b"
    Assert-Sample "object" $ObjectSamplePath 281 3 `
        "\bchlayout:3 channels \(FL\+FR\+UNK@OBJ1\)"

    Write-Output "AV3A stage-two validation passed: HOA native=4ch/s16, moving-object native=3ch/s16, binaural=stereo/f32, mpv PCM hashes match FFmpeg"
}
finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
