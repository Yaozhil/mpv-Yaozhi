param(
    [Parameter(Mandatory = $true)]
    [string]$MpvPath,

    [Parameter(Mandatory = $true)]
    [string]$FFmpegPath,

    [Parameter(Mandatory = $true)]
    [string]$SamplePath
)

$ErrorActionPreference = "Stop"

foreach ($path in @($MpvPath, $FFmpegPath, $SamplePath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}

$decoderList = & $FFmpegPath -hide_banner -decoders 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "FFmpeg decoder listing failed"
}
$decoderText = ($decoderList | ForEach-Object { "$_" }) -join "`n"
if ($decoderText -notmatch "(?m)^\s*V.*\blibvvdec\b") {
    throw "FFmpeg decoder list does not contain libvvdec"
}
if ($decoderText -notmatch "(?m)^\s*V.*\bvvc\b") {
    throw "FFmpeg decoder list does not contain the native vvc fallback"
}

function Assert-MpvDecoder {
    param(
        [AllowNull()]
        [string]$Decoder,

        [Parameter(Mandatory = $true)]
        [string]$Expected
    )

    $arguments = @(
        "--no-config",
        "--load-scripts=no",
        "--vo=null",
        "--ao=null",
        "--audio=no",
        "--hwdec=no",
        "--frames=1",
        "--msg-level=all=warn,vd=debug"
    )
    if ($Decoder) {
        $arguments += "--vd=$Decoder"
    }
    $arguments += "--"
    $arguments += $SamplePath

    $output = & $MpvPath @arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | ForEach-Object { "$_" }) -join "`n"

    if ($exitCode -ne 0) {
        $mode = if ($Decoder) { $Decoder } else { "default" }
        throw "mpv VVC playback failed for $mode decoder:`n$text"
    }

    $marker = "Selected decoder: $Expected"
    if ($text -notmatch [regex]::Escape($marker)) {
        $mode = if ($Decoder) { $Decoder } else { "default" }
        throw "mpv selected the wrong $mode VVC decoder; expected ${Expected}:`n$text"
    }
}

Assert-MpvDecoder -Decoder $null -Expected "libvvdec"
Assert-MpvDecoder -Decoder "libvvdec" -Expected "libvvdec"
Assert-MpvDecoder -Decoder "vvc" -Expected "vvc"

Write-Output "VVDEC validation passed: default=libvvdec, explicit libvvdec and native vvc fallback both decode"
