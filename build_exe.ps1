# Сборка TaskTimer link B24 для Windows (один exe, без консоли).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    python -m venv .venv
}

$Bump = if ($env:BUMP) { $env:BUMP } else { "patch" }
if (-not $env:VERSION -and $env:NO_BUMP -ne "1") {
    Write-Host "==> Semver bump ($Bump) в pyproject.toml"
    & $VenvPython "$PSScriptRoot\scripts\bump_version.py" $Bump | Out-Null
}

$Version = if ($env:VERSION) {
    $env:VERSION
} else {
    & $VenvPython -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
}
Write-Host "==> Версия пакета: $Version"

Write-Host "==> Установка зависимостей сборки"
& $VenvPython -m pip install -q -e . -r requirements-build.txt

Write-Host "==> PyInstaller (TaskTimer.spec)"
& $VenvPython -m PyInstaller --noconfirm --clean TaskTimer.spec

$ExeSrc = Join-Path $PSScriptRoot "dist\TaskTimer.exe"
if (-not (Test-Path $ExeSrc)) {
    throw "Не найден бинарник: $ExeSrc"
}

$PackageName = if ($env:PACKAGE_NAME) { $env:PACKAGE_NAME } else { "timerapp-exp" }
$ExeOut = Join-Path $PSScriptRoot "dist\$PackageName-$Version-win64.exe"
Copy-Item -Force $ExeSrc $ExeOut

Write-Host "Готово: $ExeOut" -ForegroundColor Green
Get-Item $ExeOut | Format-List Name, Length, LastWriteTime
