[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [string]$ISCCPath = $env:ISCC_PATH
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $PythonPath = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
}
if ([string]::IsNullOrWhiteSpace($ISCCPath)) {
    $ISCCPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path -LiteralPath $ISCCPath)) {
    throw "ISCC.exe was not found. Install Inno Setup 6 or set ISCC_PATH."
}

& (Join-Path $PSScriptRoot "build_windows.ps1") -PythonPath $PythonPath

$OutputDir = Join-Path $RepoRoot "installer\output"
if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}

Push-Location $RepoRoot
try {
    $Version = (
        & $PythonPath -c "import runpy; print(runpy.run_path('src/nist_biometric_viewer/__init__.py')['__version__'])"
    ).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Version)) {
        throw "Could not read the application version."
    }

    & $ISCCPath "/DAppVersion=$Version" "installer\nist_biometric_viewer.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$Installer = Join-Path $OutputDir "NistBiometricViewer_Setup_$Version.exe"
if (-not (Test-Path -LiteralPath $Installer)) {
    throw "ISCC did not produce $Installer."
}

Write-Host "Windows installer: $Installer"
