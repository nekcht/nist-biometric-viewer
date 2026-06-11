[CmdletBinding()]
param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $PythonPath = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
}

$BuildDir = Join-Path $RepoRoot "build"
$DistDir = Join-Path $RepoRoot "dist"
foreach ($Target in @($BuildDir, $DistDir)) {
    $ResolvedParent = (Resolve-Path -LiteralPath (Split-Path -Parent $Target)).Path
    if (-not $Target.StartsWith($ResolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected path: $Target"
    }
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

& $PythonPath -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed for $PythonPath. Install the project's dev dependencies."
}

Push-Location $RepoRoot
try {
    & $PythonPath -m PyInstaller "ForensicPrintComparator.spec" --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$Executable = Join-Path $DistDir "ForensicPrintComparator\ForensicPrintComparator.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "PyInstaller did not produce $Executable."
}

Write-Host "Packaged application: $Executable"
