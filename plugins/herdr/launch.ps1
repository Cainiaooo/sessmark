param([Parameter(Mandatory = $true)][string]$Mode)
$ErrorActionPreference = 'Stop'
$pluginPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $pluginPython) {
    & $pluginPython -m sessmark_herdr $Mode
} elseif (Test-Path -LiteralPath $projectPython) {
    & $projectPython -m sessmark_herdr $Mode
} else {
    & sessmark-herdr $Mode
}
exit $LASTEXITCODE
