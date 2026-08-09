param(
    [Parameter(Mandatory = $true)][string]$MpvPath,
    [Parameter(Mandatory = $true)][string]$FFmpegPath,
    [string]$SamplePath
)

$ErrorActionPreference = 'Stop'
foreach ($path in @($MpvPath, $FFmpegPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required executable not found: $path"
    }
}

$bsfs = & $FFmpegPath -hide_banner -bsfs 2>&1
if ($LASTEXITCODE -ne 0 -or (($bsfs | ForEach-Object { "$_" }) -join "`n") -notmatch '(?m)^dovi_split$') {
    throw "FFmpeg does not expose the dovi_split bitstream filter"
}

if ($SamplePath) {
    if (-not (Test-Path -LiteralPath $SamplePath -PathType Leaf)) {
        throw "FEL sample not found: $SamplePath"
    }
    $output = & $MpvPath --no-config --vo=null --ao=null --hwdec=no --frames=90 --msg-level=all=v -- $SamplePath 2>&1
    $text = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($text -match "dovi_split.+not available") {
        throw "mpv fell back to the base layer because dovi_split is unavailable"
    }
    if ($text -notmatch 'Dolby Vision Profile 7 splitter.+virtual EL stream') {
        throw "mpv did not create the Dolby Vision Profile 7 enhancement-layer stream"
    }
}

Write-Output 'Dolby Vision FEL capability validation passed'
