param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DistDir = Join-Path $ProjectRoot "dist"
$ReleasesDir = Join-Path $ProjectRoot "Releases"
$BuildDir = Join-Path $ProjectRoot "build"
$SpecFile = Join-Path $ProjectRoot "SySubs.spec"
$PyOutputDir = Join-Path $DistDir "SySubs"
$ZipFile = Join-Path $ReleasesDir "SySubs-$Version-portable.zip"

Write-Host "=== SySubs Build v$Version ===" -ForegroundColor Cyan

# 1. Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path $PyOutputDir) { Remove-Item -Recurse -Force $PyOutputDir }
$ReleasesDir = New-Item -ItemType Directory -Path $ReleasesDir -Force
if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }

# 2. Run PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Yellow
pyinstaller $SpecFile --clean --noconfirm

# 3. Copy pre-bundled tiny model
Write-Host "Copying pre-bundled tiny model..." -ForegroundColor Yellow
$ModelSrc = Join-Path $ProjectRoot "models\tiny"
$ModelDst = Join-Path $PyOutputDir "models\tiny"
if (Test-Path $ModelSrc) {
    New-Item -ItemType Directory -Path $ModelDst -Force | Out-Null
    Copy-Item -Path "$ModelSrc\*" -Destination $ModelDst -Recurse -Force
    Write-Host "  models/tiny/ copied." -ForegroundColor Green
} else {
    Write-Host "  WARNING: models/tiny/ not found. Add it manually before release." -ForegroundColor Red
}

# 4. Create portable zip
Write-Host "Creating portable zip..." -ForegroundColor Yellow
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($PyOutputDir, $ZipFile)

# 5. Clean up PyInstaller temp build folder
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }

Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Cyan
Write-Host "  Output: $PyOutputDir" -ForegroundColor Green
Write-Host "  Zip:    $ZipFile" -ForegroundColor Green
