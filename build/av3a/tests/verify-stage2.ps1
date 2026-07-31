param(
    [Parameter(Mandatory = $true)]
    [string]$FFmpegPath,

    [string]$MpvPath,

    [string]$SamplePath = (Join-Path $PSScriptRoot "hoa-order1-128k.av3a")
)

$ErrorActionPreference = "Stop"
$expectedFrames = 94
$expectedBytes = $expectedFrames * 1024 * 4 * 2
$work = Join-Path $env:TEMP ("av3a-stage2-" + [guid]::NewGuid().ToString("N"))
$nativePcm = Join-Path $work "native-s16le.pcm"
$binauralPcm = Join-Path $work "binaural-f32le.pcm"
$mpvNativePcm = Join-Path $work "mpv-native-s16le.pcm"
$mpvBinauralPcm = Join-Path $work "mpv-binaural-f32le.pcm"

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
        [string]$Mode,
        [string]$SampleFormat,
        [int]$Channels,
        [string]$ChannelLayoutPattern
    )

    $output = Invoke-Checked $FFmpegPath @(
        "-hide_banner", "-loglevel", "info",
        "-av3a_render", $Mode,
        "-i", $SamplePath,
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

try {
    New-Item -ItemType Directory -Path $work | Out-Null

    $decoderHelp = Invoke-Checked $FFmpegPath @(
        "-hide_banner",
        "-h", "decoder=libarcdav3a"
    )
    Assert-Contains $decoderHelp "\bav3a_render\b" "av3a_render decoder option"
    Assert-Contains $decoderHelp "\(default native\)" "native decoder default"

    Assert-DecodeFormat "native" "s16" 4 "\bchlayout:4 channels\b"
    Assert-DecodeFormat "binaural" "flt" 2 "\bchlayout:stereo\b"

    Invoke-Checked $FFmpegPath @(
        "-hide_banner", "-loglevel", "warning", "-y",
        "-av3a_render", "native",
        "-i", $SamplePath,
        "-map", "0:a:0",
        "-c:a", "pcm_s16le",
        "-f", "s16le",
        $nativePcm
    ) | Out-Null
    Assert-Size $nativePcm $expectedBytes

    Invoke-Checked $FFmpegPath @(
        "-hide_banner", "-loglevel", "warning", "-y",
        "-av3a_render", "binaural",
        "-i", $SamplePath,
        "-map", "0:a:0",
        "-c:a", "pcm_f32le",
        "-f", "f32le",
        $binauralPcm
    ) | Out-Null
    Assert-Size $binauralPcm $expectedBytes

    if ($MpvPath) {
        $nativeMpvOutput = Invoke-Checked $MpvPath @(
            "--no-config",
            "--vo=null",
            "--ao=pcm",
            "--ao-pcm-waveheader=no",
            "--ao-pcm-file=$mpvNativePcm",
            "--audio-display=no",
            "--audio-format=s16",
            "--audio-samplerate=48000",
            "--audio-channels=unknown4",
            "--ad-lavc-o=av3a_render=native",
            $SamplePath
        )
        Assert-NotContains $nativeMpvOutput `
            "Converting libavcodec frame to mpv frame failed" `
            "libavcodec-to-mpv frame conversion failure"
        Assert-Size $mpvNativePcm $expectedBytes
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
            $SamplePath
        )
        Assert-NotContains $binauralMpvOutput `
            "Cannot open Libavresample context|libswresample failed to initialize" `
            "binaural resampler initialization failure"
        Assert-Size $mpvBinauralPcm $expectedBytes
        Assert-SameHash $binauralPcm $mpvBinauralPcm
    }

    Write-Output "AV3A stage-two validation passed: native=4ch/s16, binaural=stereo/f32, mpv PCM hashes match FFmpeg"
}
finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
