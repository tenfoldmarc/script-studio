# Script Studio quiet check (Windows). Runs on Claude Creator Studio's own Python; sets it up through the Studio
# when it is missing, then prints the STATUS lines.
$ErrorActionPreference = 'SilentlyContinue'
$SsDir = Split-Path -Parent $PSScriptRoot
$Local = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData\Local' }
$Plat = Join-Path $Local 'video-studio\.platform.json'

function Find-Py {
  if (-not (Test-Path $Plat)) { return $null }
  $j = Get-Content $Plat -Raw | ConvertFrom-Json
  if ($j.python -and (Test-Path $j.python)) { return $j.python }
  return $null
}

$Py = Find-Py
if (-not $Py) {
  $Studio = Get-ChildItem -Path (Join-Path $HOME '.claude\plugins\cache\*\video-studio\*\skills\video-studio\scripts\start.ps1') |
    Sort-Object FullName | Select-Object -Last 1
  if (-not $Studio) { Write-Output 'STATUS studio NOT_INSTALLED'; exit 0 }
  Write-Output 'SETUP running the Creator Studio setup first (one time, a few minutes)'
  powershell -NoProfile -ExecutionPolicy Bypass -File $Studio.FullName | Out-Null
  $Py = Find-Py
  if (-not $Py) { Write-Output 'STATUS studio SETUP_FAILED'; exit 0 }
}
Write-Output "PY $Py"
& $Py (Join-Path $SsDir 'scripts\ss.py') check
