param(
    [Parameter(Mandatory = $true)][string]$MpvPath,
    [Parameter(Mandatory = $true)][string]$FFmpegPath,
    [string]$SamplePath,
    [string]$DualTrackSamplePath,
    [string]$BluRayIsoPath
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

function Get-MpvProbeText {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "FEL sample not found: $Path"
    }
    $output = & $MpvPath --no-config --vo=null --ao=null --hwdec=no --frames=90 `
        --msg-level=all=v `
        '--term-playing-msg=FELTRACK ${current-tracks/video/dolby-vision-profile}' `
        -- $Path 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "mpv FEL probe failed with exit code $LASTEXITCODE for $Path"
    }
    return ($output | ForEach-Object { "$_" }) -join "`n"
}

if ($SamplePath) {
    $text = Get-MpvProbeText -Path $SamplePath
    if ($text -match "dovi_split.+not available") {
        throw "mpv fell back to the base layer because dovi_split is unavailable"
    }
    if ($text -notmatch 'Dolby Vision Profile 7 splitter.+virtual EL stream') {
        throw "mpv did not create the Dolby Vision Profile 7 enhancement-layer stream"
    }
    if ($text -notmatch 'Dolby Vision Profile 7 enhancement layer: enabled complete seek recovery') {
        throw "mpv did not enable targeted seek recovery for the virtual Profile 7 EL"
    }
}

if ($DualTrackSamplePath) {
    $text = Get-MpvProbeText -Path $DualTrackSamplePath
    if ($text -notmatch '(Found Dolby Vision config record: profile 7|Dolby Vision Profile 7 splitter.+virtual EL stream)') {
        throw "mpv did not detect Dolby Vision Profile 7 metadata in the dual-track sample"
    }
    if ($text -notmatch '(?m)^.*\[vf\] \[el_pair\].*$') {
        throw "mpv did not pair the Dolby Vision base and enhancement tracks"
    }
    if ($text -notmatch '(?m)^FELTRACK 7\s*$') {
        throw "mpv did not expose Profile 7 metadata on the selectable base-layer track"
    }
    if ($text -notmatch 'Dolby Vision Profile 7 enhancement layer: enabled complete seek recovery') {
        throw "mpv did not enable targeted seek recovery for the paired Profile 7 EL"
    }
}

if ($BluRayIsoPath) {
    if (-not (Test-Path -LiteralPath $BluRayIsoPath -PathType Leaf)) {
        throw "Blu-ray FEL ISO not found: $BluRayIsoPath"
    }
    $output = & $MpvPath --no-config --vo=null --ao=null --hwdec=no --frames=90 `
        --msg-level=all=v `
        '--term-playing-msg=FELTRACK ${current-tracks/video/dolby-vision-profile}' `
        "--bluray-device=$BluRayIsoPath" 'bd://' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "mpv Blu-ray FEL probe failed with exit code $LASTEXITCODE"
    }
    $text = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($text -notmatch '(?m)^.*\[vf\] \[el_pair\].*$') {
        throw "mpv did not pair the Blu-ray Dolby Vision base and enhancement streams from the authored relation"
    }
    if ($text -notmatch '(?m)^FELTRACK 7\s*$') {
        throw "mpv did not expose Profile 7 metadata for Blu-ray playback"
    }
    if ($text -notmatch 'Dolby Vision Profile 7 enhancement layer: enabled complete seek recovery') {
        throw "mpv did not enable targeted seek recovery for the authored Blu-ray Profile 7 EL"
    }
}

Write-Output 'Dolby Vision FEL capability validation passed'
