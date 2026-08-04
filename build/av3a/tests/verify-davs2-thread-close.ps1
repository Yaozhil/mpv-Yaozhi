param(
    [Parameter(Mandatory = $true)]
    [string]$MpvPath,

    [string]$WorkDir = "",

    [ValidateRange(1, 100)]
    [int]$Iterations = 16
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $MpvPath -PathType Leaf)) {
    throw "Required mpv executable not found: $MpvPath"
}

if (-not $WorkDir) {
    $WorkDir = Join-Path $env:TEMP "mpv-davs2-thread-close-validation"
}
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$samplePath = Join-Path $WorkDir "probe.avs2"
[IO.File]::WriteAllBytes(
    $samplePath,
    [byte[]](
        0x00, 0x00, 0x01, 0xB0,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x01, 0xB3,
        0x00, 0x00, 0x00, 0x00
    )
)

$arguments = @(
    "--no-config",
    "--load-scripts=no",
    "--vo=null",
    "--ao=null",
    "--audio=no",
    "--hwdec=no",
    "--vd=libdavs2",
    "--vd-lavc-threads=13",
    "--demuxer=lavf",
    "--demuxer-lavf-format=avs2",
    "--frames=1",
    "--msg-level=all=warn,vd=debug",
    "--",
    $samplePath
)

for ($iteration = 1; $iteration -le $Iterations; $iteration++) {
    $stdoutPath = Join-Path $WorkDir "stdout-$iteration.txt"
    $stderrPath = Join-Path $WorkDir "stderr-$iteration.txt"
    $process = Start-Process `
        -FilePath $MpvPath `
        -ArgumentList $arguments `
        -Wait `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $exitCode = [int32]$process.ExitCode
    $stdout = Get-Content -Raw -LiteralPath $stdoutPath
    $stderr = Get-Content -Raw -LiteralPath $stderrPath
    $output = $stdout + "`n" + $stderr

    if ($output -notmatch "Selected decoder:\s+libdavs2") {
        throw "Iteration $iteration did not initialize libdavs2:`n$output"
    }
    if ($exitCode -notin @(0, 2)) {
        $unsignedExit = [BitConverter]::ToUInt32(
            [BitConverter]::GetBytes($exitCode),
            0
        )
        $exitHex = "0x{0:X8}" -f $unsignedExit
        throw "Iteration $iteration crashed or returned an unexpected exit code ${exitCode} (${exitHex}):`n$output"
    }
}

Write-Output "davs2 thread-close validation passed: $Iterations open/close iterations"
