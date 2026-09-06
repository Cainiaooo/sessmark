param([Parameter(Mandatory = $true)][string]$Mode)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $pythonExe) {
    & $pythonExe -m sessmark_herdr $Mode
} else {
    & sessmark-herdr $Mode
}
exit $LASTEXITCODE
