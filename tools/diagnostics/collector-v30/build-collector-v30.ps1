# CPU-only Windows runner build. This script never starts an ETW session.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$WorkRoot)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$collectorCommit = '717c5bf14e80a4a06b70cd16415ae8d40a7ce201'
$collectorWork = [IO.Path]::GetFullPath($WorkRoot)
if (Test-Path -LiteralPath $collectorWork) { throw 'WorkRoot exists; use a fresh isolated build directory' }
New-Item -ItemType Directory -Path $collectorWork | Out-Null
$collectorSource = Join-Path $collectorWork 'official-source'
$collectorOutput = Join-Path $collectorWork 'artifact'
$collectorObjects = Join-Path $collectorWork 'obj'
New-Item -ItemType Directory -Path $collectorOutput, $collectorObjects | Out-Null

function Invoke-CollectorNative {
    param([string]$Executable, [string[]]$Arguments, [string]$LogName, [int]$ExpectedExit = 0)
    $collectorLines = & $Executable @Arguments 2>&1
    $collectorExit = $LASTEXITCODE
    $collectorLines | ForEach-Object { $_.ToString() } | Set-Content -LiteralPath (Join-Path $collectorOutput $LogName) -Encoding utf8
    if ($collectorExit -ne $ExpectedExit) { throw "$LogName exit $collectorExit; expected $ExpectedExit. Log retained." }
}

Invoke-CollectorNative 'git' @('-c', 'core.autocrlf=false', 'clone', '--depth', '1', '--branch', 'v2.3.1',
    'https://github.com/GameTechDev/PresentMon.git', $collectorSource) 'clone.log'
$collectorHead = (& git -C $collectorSource rev-parse HEAD).Trim()
$collectorTagHead = (& git -C $collectorSource rev-parse 'refs/tags/v2.3.1^{commit}').Trim()
if ($LASTEXITCODE -ne 0 -or $collectorHead -ne $collectorCommit -or $collectorTagHead -ne $collectorCommit) {
    throw 'Official v2.3.1 tag no longer resolves to reviewed full commit'
}
if ((& git -C $collectorSource status --porcelain) -or $LASTEXITCODE -ne 0) { throw 'Official source is not pristine' }

$collectorVsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$collectorVsPath = (& $collectorVsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
if ($LASTEXITCODE -ne 0 -or -not $collectorVsPath) { throw 'VS x64 tools absent; no package installation attempted' }
& (Join-Path $collectorVsPath 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
if ($env:VSCMD_ARG_TGT_ARCH -notin @('x64', 'amd64')) { throw 'Developer shell target is not x64' }
Get-Command cl.exe, link.exe | Select-Object Name, Source | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $collectorOutput 'compiler-paths.json') -Encoding utf8

$collectorTraceSource = Join-Path $collectorSource 'PresentData/PresentMonTraceSession.cpp'
Copy-Item -LiteralPath $collectorTraceSource -Destination (Join-Path $collectorObjects 'baseline-session.cpp')
Invoke-CollectorNative 'python' @((Join-Path $PSScriptRoot 'apply-start-buffers.py'), '--source-root', $collectorSource,
    '--receipt', (Join-Path $collectorOutput 'patch-receipt.json')) 'patch.log'
$collectorDirty = @(& git -C $collectorSource diff --name-only)
$collectorNumstat = @(& git -C $collectorSource diff --numstat)
if ($LASTEXITCODE -ne 0 -or $collectorDirty.Count -ne 1 -or $collectorDirty[0] -ne 'PresentData/PresentMonTraceSession.cpp' -or
    $collectorNumstat.Count -ne 1 -or $collectorNumstat[0] -ne "2`t0`tPresentData/PresentMonTraceSession.cpp") {
    throw 'Source delta escaped exactly two additions in StartTrace source'
}

# Official console source lists plus its required Hash.cpp implementation.
# No GUI/service/CommonUtilities project or vcpkg dependency is built.
# No official project/source is rewritten. This is an isolated diagnostic build.
$collectorPresentData = @('Debug.cpp', 'GpuTrace.cpp', 'PresentMonTraceConsumer.cpp', 'TraceConsumer.cpp', 'PresentMonTraceSession.cpp')
$collectorConsole = @('CommandLine.cpp', 'Console.cpp', 'ConsumerThread.cpp', 'CsvOutput.cpp', 'MainThread.cpp', 'OutputThread.cpp', 'Privilege.cpp')
$collectorGenerated = Join-Path $collectorObjects 'generated'
New-Item -ItemType Directory -Path $collectorGenerated | Out-Null
[IO.File]::WriteAllText((Join-Path $collectorGenerated 'version.h'), 'char const* PRESENT_MON_VERSION = "2.3.1";' + "`n", [Text.UTF8Encoding]::new($false))
$collectorCommonFlags = @('/nologo', '/c', '/O2', '/MT', '/EHsc', '/Gy', '/Oi', '/GS', '/DNDEBUG', '/DUNICODE', '/D_UNICODE')
$collectorWinFlags = @('/D_WIN32_WINNT=0x0601', '/DNTDDI_VERSION=0x06010000', '/DWIN32_LEAN_AND_MEAN')
$collectorInputHashes = [ordered]@{}
$collectorObjectFiles = @()
$collectorCompileCommands = @()
foreach ($collectorUnit in $collectorPresentData + $collectorConsole + @('Hash.cpp')) {
    $collectorCategory = if ($collectorUnit -eq 'Hash.cpp') { 'Hash' } elseif ($collectorUnit -in $collectorPresentData) { 'PresentData' } else { 'PresentMon' }
    $collectorRelative = if ($collectorCategory -eq 'Hash') { 'IntelPresentMon/CommonUtilities/Hash.cpp' } else { "$collectorCategory/$collectorUnit" }
    $collectorFile = Join-Path $collectorSource $collectorRelative
    $collectorObject = Join-Path $collectorObjects ($collectorCategory + '-' + [IO.Path]::GetFileNameWithoutExtension($collectorUnit) + '.obj')
    $collectorFlags = $collectorCommonFlags + @('/Fo' + $collectorObject)
    if ($collectorCategory -ne 'Hash') { $collectorFlags += $collectorWinFlags }
    if ($collectorCategory -eq 'PresentMon') { $collectorFlags += @('/std:c++17', '/D_CONSOLE', '/I' + $collectorObjects) }
    else { $collectorFlags += @('/std:c++latest') }
    if ($collectorCategory -eq 'PresentData') { $collectorFlags += @('/D_LIB', '/sdl') }
    $collectorFlags += @($collectorFile)
    $collectorInputHashes[$collectorRelative] = (Get-FileHash -LiteralPath $collectorFile -Algorithm SHA256).Hash.ToLowerInvariant()
    $collectorCompileCommands += ,$collectorFlags
    Invoke-CollectorNative 'cl.exe' $collectorFlags ('compile-' + $collectorCategory + '-' + $collectorUnit + '.log')
    $collectorObjectFiles += $collectorObject
}
$collectorLibraries = @('advapi32.lib', 'shell32.lib', 'tdh.lib', 'user32.lib')
$collectorExe = Join-Path $collectorOutput 'PresentMon-2.3.1-v30-buffers-x64.exe'
Invoke-CollectorNative 'link.exe' (@('/nologo', '/MACHINE:X64', '/SUBSYSTEM:CONSOLE', '/OPT:REF', '/OPT:ICF', '/OUT:' + $collectorExe) + $collectorObjectFiles + $collectorLibraries) 'link-console.log'

# Execute property construction from the actual official source, with its first
# StartTraceW symbol replaced in this separate probe translation unit only.
# The hook returns ACCESS_DENIED; providers/trace/Stop paths are never entered.
$collectorProbeSupport = $collectorObjectFiles | Where-Object {
    [IO.Path]::GetFileName($_) -like 'PresentData-*' -and [IO.Path]::GetFileName($_) -ne 'PresentData-PresentMonTraceSession.obj'
}
$collectorProbeSupport += Join-Path $collectorObjects 'Hash-Hash.obj'
foreach ($collectorProbeVariant in @('baseline', 'patched')) {
    $collectorProbeObject = Join-Path $collectorObjects ('probe-' + $collectorProbeVariant + '.obj')
    $collectorProbeFlags = $collectorCommonFlags + $collectorWinFlags + @('/std:c++latest', '/I' + (Join-Path $collectorSource 'PresentData'),
        '/I' + $collectorObjects, '/Fo' + $collectorProbeObject)
    if ($collectorProbeVariant -eq 'baseline') { $collectorProbeFlags += @('/DPM_PROBE_BASELINE') }
    $collectorProbeFlags += Join-Path $PSScriptRoot 'verify-start-props.cpp'
    Invoke-CollectorNative 'cl.exe' $collectorProbeFlags ('compile-probe-' + $collectorProbeVariant + '.log')
    $collectorProbeExe = Join-Path $collectorOutput ('verify-start-props-' + $collectorProbeVariant + '.exe')
    Invoke-CollectorNative 'link.exe' (@('/nologo', '/MACHINE:X64', '/SUBSYSTEM:CONSOLE', '/OPT:REF', '/OPT:ICF', '/OUT:' + $collectorProbeExe,
        $collectorProbeObject) + $collectorProbeSupport + $collectorLibraries) ('link-probe-' + $collectorProbeVariant + '.log')
    Invoke-CollectorNative $collectorProbeExe @() ('props-' + $collectorProbeVariant + '.json')
}
Invoke-CollectorNative $collectorExe @('--help') 'help.txt' 1
# Official 2.3.1 has no --version option. Keep and verify its failure/banner.
Invoke-CollectorNative $collectorExe @('--version') 'version-invalid.txt' 1
@{ help_exit_code = 1; version_exit_code = 1 } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $collectorOutput 'parser-receipt.json') -Encoding utf8
Invoke-CollectorNative 'python' @((Join-Path $PSScriptRoot 'verify-compiled-probes.py'), '--artifact-dir', $collectorOutput) 'compiled-check.log'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'start-buffers-only.patch') -Destination $collectorOutput
$collectorReceipt = [ordered]@{
    status = 'BUILT_ISOLATED_DIAGNOSTIC_NOT_PLAYER_DELIVERY'; official_repository = 'GameTechDev/PresentMon';
    official_tag = 'v2.3.1'; official_commit = $collectorCommit; diagnostic_source_changes = 'two StartTrace buffer assignments only';
    build_strategy = 'explicit official console/PresentData units plus required official Hash.cpp; projects unmodified';
    build_flags = $collectorCompileCommands; source_unit_sha256 = $collectorInputHashes;
    exe_sha256 = (Get-FileHash -LiteralPath $collectorExe -Algorithm SHA256).Hash.ToLowerInvariant();
    VSInstallPath = $collectorVsPath; VSCMD_VER = $env:VSCMD_VER; WindowsSDKVersion = $env:WindowsSDKVersion;
    tools_script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();
    no_live_ETW_capture = $true; no_player_run = $true; no_existing_session_access = $true; formal_Display_acceptance = $false
}
$collectorReceipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $collectorOutput 'build-receipt.json') -Encoding utf8
Write-Output ('Prepared artifact: ' + $collectorOutput)
