[CmdletBinding()]
param(
    [string]$Output = "output",
    [ValidateRange(1, 300)]
    [int]$Timeout = 30,
    [switch]$NoShow
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "No se encontró .venv. Créelo con: python -m venv .venv"
}

$Arguments = @(
    (Join-Path $ProjectRoot "script.py")
    "--output", $Output
    "--timeout", $Timeout
)

if ($NoShow) {
    $Arguments += "--no-show"
}

& $Python @Arguments
exit $LASTEXITCODE
