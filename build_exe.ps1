# Сборка TaskTimer.exe (один файл, без консоли).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -e . -r requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean TaskTimer.spec

Write-Host "Готово: dist\TaskTimer.exe" -ForegroundColor Green
