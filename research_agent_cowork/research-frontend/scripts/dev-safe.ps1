param(
  [int]$Port = 3001,
  [switch]$RepairOnly
)

$ErrorActionPreference = "SilentlyContinue"

$projectRoot = (Resolve-Path ".").Path

# Kill all Next.js node processes for this project to avoid stale/corrupt dev state.
$projectNextProcs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine -like "*$projectRoot*" -and
    $_.CommandLine -like "*node_modules\\next\\dist\\*"
  }

foreach ($proc in $projectNextProcs) {
  Stop-Process -Id $proc.ProcessId -Force
}

# Also free target port if still occupied by any process.
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen | Select-Object -First 1
if ($listener) { Stop-Process -Id $listener.OwningProcess -Force }

# Remove Next build cache with retries.
if (Test-Path ".next") {
  $removed = $false
  for ($i = 0; $i -lt 3; $i++) {
    try {
      Remove-Item ".next" -Recurse -Force
      $removed = $true
      break
    } catch {
      Start-Sleep -Milliseconds 300
    }
  }

  if (-not $removed -and (Test-Path ".next")) {
    Write-Error "Failed to remove .next cache. Close IDE tasks and retry."
    exit 1
  }
}

$ErrorActionPreference = "Continue"

if ($RepairOnly) {
  Write-Host "Repair complete (.next cleared, stale Next processes stopped)."
  exit 0
}

Write-Host "Starting Next dev server on port $Port ..."
& node .\node_modules\next\dist\bin\next dev -p $Port
