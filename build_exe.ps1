# Сборка TaskTimer.exe (один файл, без консоли).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean TaskTimer.spec

Write-Host "Готово: dist\TaskTimer.exe" -ForegroundColor Green
