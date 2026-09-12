param([switch]$AllowCompleted)
$validator = Join-Path $PSScriptRoot "..\..\.agent\validate-backlog.ps1"
if (-not (Test-Path -LiteralPath $validator)) { throw "Backlog validator not found" }
& $validator @PSBoundParameters
