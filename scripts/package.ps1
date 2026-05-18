param(
    [string]$Version = "1.0.0",
    [string]$PythonVersion = "3.11.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$TempDir = Join-Path $ProjectRoot "portable_build"
$OutputDir = Join-Path $TempDir "SySubs-portable"
$PythonDir = Join-Path $OutputDir "python"
$ZipFile = Join-Path (Join-Path $ProjectRoot "Releases") "SySubs-$Version-portable.zip"

Write-Host "=== SySubs Portable Build v$Version ===" -ForegroundColor Cyan

# Clean
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

# 1. Download Python embeddable
$PyUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PyZip = Join-Path $TempDir "python-embed.zip"
Write-Host "Downloading Python $PythonVersion embeddable..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $PyUrl -OutFile $PyZip -UseBasicParsing -ErrorAction Stop
} catch {
    Write-Host "  ERROR: Failed to download Python: $_" -ForegroundColor Red
    exit 1
}
Write-Host "  Extracting..."
Expand-Archive -Path $PyZip -DestinationPath $PythonDir
Remove-Item $PyZip

# 2. Copy Tcl/Tk from system Python (same version assumed)
$SysPrefix = python -c "import sys; print(sys.base_prefix)"
$SysTcl = Join-Path $SysPrefix "tcl"
$SysDlls = Join-Path $SysPrefix "DLLs"
if (Test-Path $SysTcl) {
    Write-Host "Copying Tcl/Tk from system Python..." -ForegroundColor Yellow
    Copy-Item -Path $SysTcl -Destination $PythonDir -Recurse -Force
    # Copy Tcl/Tk DLLs alongside _tkinter.pyd (in python root)
    foreach ($dll in @("tcl86t.dll", "tk86t.dll")) {
        $srcDll = Join-Path $SysDlls $dll
        if (Test-Path $srcDll) {
            Copy-Item -Path $srcDll -Destination (Join-Path $PythonDir $dll) -Force
            Write-Host "  Copied $dll"
        }
    }
} else {
    Write-Host "  WARNING: Tcl/Tk not found at $SysTcl" -ForegroundColor Red
}

# 3. Copy standard library modules not in embeddable's python311.zip
#    (tkinter Python wrapper - _tkinter.pyd is already in the embeddable)
$SysLib = Join-Path $SysPrefix "Lib"
$EmbLib = Join-Path $PythonDir "Lib"
New-Item -ItemType Directory -Path $EmbLib -Force | Out-Null
if (Test-Path "$SysLib\tkinter") {
    Write-Host "Copying tkinter library..." -ForegroundColor Yellow
    Copy-Item -Path "$SysLib\tkinter" -Destination $EmbLib -Recurse -Force -Exclude "__pycache__"
}

# Copy _tkinter.pyd C extension from system DLLs (embeddable lacks it)
foreach ($pyd in @("_tkinter.pyd")) {
    $srcPyd = Join-Path $SysDlls $pyd
    if (Test-Path $srcPyd) {
        Copy-Item -Path $srcPyd -Destination (Join-Path $PythonDir $pyd) -Force
        Write-Host "  Copied $pyd"
    }
}

# 4. Enable site-packages and Lib in _pth file
$PthFile = Join-Path $PythonDir "python*._pth"
$PthFile = Resolve-Path $PthFile | Select-Object -ExpandProperty Path
if ($PthFile) {
@"
python311.zip
.
Lib
Lib\site-packages
import site
"@ | Set-Content $PthFile
    Write-Host "  _pth file configured: $PthFile" -ForegroundColor Green
}

# Create sitecustomize.py to make app root importable
# (the _pth file disables CWD+script dir from sys.path)
$SitePkg = Join-Path $PythonDir "Lib\site-packages"
New-Item -ItemType Directory -Path $SitePkg -Force | Out-Null
@"
import sys
import pathlib
# Add app root (parent of python/) to sys.path so main.py and subpackages
# (infra/, services/, ui/) are importable regardless of CWD.
_app_root = pathlib.Path(sys.executable).parent.parent
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))
"@ | Out-File -FilePath (Join-Path $SitePkg "sitecustomize.py") -Encoding utf8
Write-Host "  sitecustomize.py created" -ForegroundColor Green

# 4. Bootstrap pip
Write-Host "Bootstrapping pip..." -ForegroundColor Yellow
$GetPip = Join-Path $TempDir "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip -UseBasicParsing
& "$PythonDir\python.exe" $GetPip --no-warn-script-location 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: pip bootstrap failed" -ForegroundColor Red
    exit 1
}

# 5. Install dependencies
Write-Host "Installing dependencies (this may take a while)..." -ForegroundColor Yellow
& "$PythonDir\python.exe" -m pip install faster-whisper customtkinter --no-warn-script-location 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: pip install failed" -ForegroundColor Red
    exit 1
}

# 6. Strip unneeded weight from bundled packages (optional — comment out to keep full install)
Write-Host "Cleaning pip cache..." -ForegroundColor Yellow
& "$PythonDir\python.exe" -m pip cache purge 2>&1 | Out-Null

# 7. Copy application files
Write-Host "Copying application files..." -ForegroundColor Yellow
Copy-Item -Path "$ProjectRoot\main.py" -Destination $OutputDir
Copy-Item -Path "$ProjectRoot\constants.py" -Destination $OutputDir
Copy-Item -Path "$ProjectRoot\ui" -Destination $OutputDir -Recurse -Exclude "__pycache__"
Copy-Item -Path "$ProjectRoot\services" -Destination $OutputDir -Recurse -Exclude "__pycache__"
Copy-Item -Path "$ProjectRoot\infra" -Destination $OutputDir -Recurse -Exclude "__pycache__"
Copy-Item -Path "$ProjectRoot\assets" -Destination $OutputDir -Recurse

# 8. Copy ffmpeg
$FfmpegSrc = Join-Path $ProjectRoot "ffmpeg.exe"
if (Test-Path $FfmpegSrc) {
    Write-Host "Copying ffmpeg.exe..." -ForegroundColor Yellow
    Copy-Item -Path $FfmpegSrc -Destination $OutputDir
} else {
    Write-Host "  WARNING: ffmpeg.exe not found at $FfmpegSrc" -ForegroundColor Red
}

# 9. Copy models
$ModelSrc = Join-Path $ProjectRoot "models\tiny"
$ModelDst = Join-Path $OutputDir "models\tiny"
if (Test-Path $ModelSrc) {
    Write-Host "Copying tiny model..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $ModelDst -Force | Out-Null
    Copy-Item -Path "$ModelSrc\*" -Destination $ModelDst -Recurse -Force
} else {
    Write-Host "  WARNING: models/tiny/ not found" -ForegroundColor Red
}

# 10. Create launchers
Write-Host "Creating launchers..." -ForegroundColor Yellow
@"
@echo off
cd /d "%~dp0"
start /b "" "%~dp0python\pythonw.exe" "%~dp0main.py"
"@ | Out-File -FilePath "$OutputDir\SySubs.bat" -Encoding ascii
@"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\python\pythonw.exe" & chr(34) & " " & chr(34) & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\main.py" & chr(34), 0, False
"@ | Out-File -FilePath "$OutputDir\SySubs.vbs" -Encoding ascii

# 11. Strip __pycache__ from build output (including pip-installed packages)
Get-ChildItem -Path $OutputDir -Recurse -Directory -Filter "__pycache__" -Force | Remove-Item -Recurse -Force

# 12. Create zip
Write-Host "Creating portable zip..." -ForegroundColor Yellow
$ReleasesDir = Join-Path $ProjectRoot "Releases"
New-Item -ItemType Directory -Path $ReleasesDir -Force | Out-Null
if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($OutputDir, $ZipFile)

# 12. Clean temp build dir
Remove-Item -Recurse -Force $TempDir

Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Cyan
Write-Host "  Output: $OutputDir" -ForegroundColor Green
Write-Host "  Zip:    $ZipFile" -ForegroundColor Green
