param(
    [Parameter(Mandatory = $true)]
    [string]$FFmpegPath,

    [Parameter(Mandatory = $true)]
    [string]$MpvPath,

    [Parameter(Mandatory = $true)]
    [string]$WorkDir
)

$ErrorActionPreference = "Stop"

function Invoke-Captured {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & $FilePath @Arguments 2>&1
    return @{
        ExitCode = $LASTEXITCODE
        Text = ($output | ForEach-Object { "$_" }) -join "`n"
    }
}

New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null

$demuxers = Invoke-Captured -FilePath $FFmpegPath -Arguments @(
    "-hide_banner", "-demuxers"
)
if ($demuxers.ExitCode -ne 0 -or $demuxers.Text -notmatch "(?m)^\s*D\s+webp_anim\s") {
    throw "FFmpeg Animated WebP demuxer is unavailable.`n$($demuxers.Text)"
}

$decoders = Invoke-Captured -FilePath $FFmpegPath -Arguments @(
    "-hide_banner", "-decoders"
)
if ($decoders.ExitCode -ne 0 -or $decoders.Text -notmatch "(?m)^\s*V\S*\s+webp_anim\s") {
    throw "FFmpeg Animated WebP decoder is unavailable.`n$($decoders.Text)"
}

$binaryText = [Text.Encoding]::ASCII.GetString(
    [IO.File]::ReadAllBytes($FFmpegPath)
)
if ($binaryText.Contains("SBR with 960 frame length")) {
    throw "FFmpeg still contains the former HE-AAC 960 unsupported path"
}

$animatedWebpBase64 =
    "UklGRrQAAABXRUJQVlA4WAoAAAASAAAAAwAAAwAAQU5JTQYAAAAAAAAAAABBTk1G" +
    "KAAAAAAAAAAAAAMAAAMAAFAAAAJWUDhMDwAAAC8DwAAABxD9j/4HIqL/AQBBTk1G" +
    "KAAAAAAAAAAAAAMAAAMAAHgAAAJWUDhMDwAAAC8DwAAQB9D/iAIGIqL/AQBBTk1G" +
    "KAAAAAAAAAAAAAMAAAMAAKAAAABWUDhMDwAAAC8DwAAABxDR//4HIqL/AQA="
$sample = Join-Path $WorkDir "animated-three-frame.webp"
[IO.File]::WriteAllBytes($sample, [Convert]::FromBase64String($animatedWebpBase64))

$framehash = Invoke-Captured -FilePath $FFmpegPath -Arguments @(
    "-hide_banner",
    "-v", "warning",
    "-i", $sample,
    "-map", "0:v:0",
    "-frames:v", "3",
    "-pix_fmt", "bgra",
    "-f", "framehash",
    "-hash", "sha256",
    "-"
)
if ($framehash.ExitCode -ne 0) {
    throw "FFmpeg Animated WebP decode failed.`n$($framehash.Text)"
}
if ($framehash.Text -match "skipping unsupported chunk:\s+(ANIM|ANMF)") {
    throw "FFmpeg fell back to the legacy static WebP decoder"
}
$decodedFrames = @(
    $framehash.Text -split "`n" | Where-Object { $_ -match "^\s*0,\s*\d+," }
)
if ($decodedFrames.Count -ne 3) {
    throw "Expected three Animated WebP frames, decoded $($decodedFrames.Count).`n$($framehash.Text)"
}

$mpvDecode = Invoke-Captured -FilePath $MpvPath -Arguments @(
    "--no-config",
    "--vo=null",
    "--ao=null",
    "--frames=3",
    "--msg-level=all=warn,demux=debug,vd=debug",
    $sample
)
if ($mpvDecode.ExitCode -ne 0) {
    throw "mpv Animated WebP playback failed.`n$($mpvDecode.Text)"
}
if ($mpvDecode.Text -notmatch "webp_anim") {
    throw "mpv did not select the Animated WebP path.`n$($mpvDecode.Text)"
}
if ($mpvDecode.Text -match "skipping unsupported chunk:\s+(ANIM|ANMF)") {
    throw "mpv used the legacy static WebP decoder"
}

Write-Host "FFmpeg 9.0 playback backports verified: Animated WebP 3/3 frames; HE-AAC 960 rejection removed."
