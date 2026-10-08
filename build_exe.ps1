# Build LyricVisualizer.exe from lyric_visualizer_windows.py
#
# Run from the folder that contains lyric_visualizer_windows.py:
#   powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
#   powershell -ExecutionPolicy Bypass -File .\build_exe.ps1 -PyVersion 3.12
#
# Output:
#   dist\LyricVisualizer\LyricVisualizer.exe   (folder build, recommended)
#   LyricVisualizer-win64.zip                  (zip of that folder, for sharing)
#   SHA256 hashes printed at the end

param([string]$PyVersion = "3.9")

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path "lyric_visualizer_windows.py")) {
    throw "lyric_visualizer_windows.py not found in $here"
}

Write-Host "==> Creating a clean build environment (Python $PyVersion)" -ForegroundColor Cyan
if (Test-Path ".build-venv") { Remove-Item ".build-venv" -Recurse -Force }
py -$PyVersion -m venv .build-venv
$py = Join-Path $here ".build-venv\Scripts\python.exe"

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
& $py -m pip install --upgrade pip
& $py -m pip install pygame requests `
    winrt-runtime winrt-Windows.Media.Control `
    winrt-Windows.Foundation winrt-Windows.Foundation.Collections `
    pyinstaller

Write-Host "==> Building executable" -ForegroundColor Cyan
# --noupx     : UPX-packed files are flagged by antivirus far more often
# --windowed  : no console window (errors will not be visible; drop this flag to debug)
# folder build (default) is used instead of --onefile: it starts faster and
# triggers fewer antivirus false positives
& $py -m PyInstaller --noconfirm --clean --noupx --windowed `
    --name LyricVisualizer `
    --collect-all winrt.runtime `
    --collect-all winrt.windows.media.control `
    --collect-all winrt.windows.foundation `
    --collect-all winrt.windows.foundation.collections `
    lyric_visualizer_windows.py

$exe = "dist\LyricVisualizer\LyricVisualizer.exe"
if (-not (Test-Path $exe)) { throw "Build failed: $exe not found" }

Write-Host "==> Creating zip" -ForegroundColor Cyan
$zip = "LyricVisualizer-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\LyricVisualizer\*" -DestinationPath $zip

Write-Host "==> SHA-256 hashes" -ForegroundColor Cyan
Get-FileHash $exe -Algorithm SHA256 | Format-List Hash, Path
Get-FileHash $zip -Algorithm SHA256 | Format-List Hash, Path

Write-Host ""
Write-Host "Done. Test it: .\$exe  (open Spotify and play a song first)" -ForegroundColor Green
Write-Host "This build is NOT digitally signed yet." -ForegroundColor Yellow
