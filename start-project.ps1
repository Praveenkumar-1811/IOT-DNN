$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendDirectory = Join-Path $projectRoot "frontend"

if (-not (Test-Path $python)) {
    throw "Project Python environment not found: $python"
}
if (-not (Test-Path (Join-Path $frontendDirectory "node_modules"))) {
    throw "Frontend dependencies not found. Run npm --prefix frontend install first."
}

$backendListeners = Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue
$hostBackendListener = $backendListeners | Where-Object { $_.LocalAddress -in @("0.0.0.0", "::") } | Select-Object -First 1
if ($backendListeners -and -not $hostBackendListener) {
    throw "Backend on port 8001 is bound only to loopback. Restart it with --host 0.0.0.0 for Wokwi access."
}
if ($hostBackendListener) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 3
        if ($health.status -ne "ok") {
            throw "Backend port 8001 is occupied by an unhealthy service."
        }
        Write-Output "Backend already healthy at http://127.0.0.1:8001"
    } catch {
        throw "Backend port 8001 is occupied but did not return healthy status: $($_.Exception.Message)"
    }
} else {
    Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload") `
        -WorkingDirectory $projectRoot
    Write-Output "Started backend at http://127.0.0.1:8001"
}

$frontendListener = Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($frontendListener) {
    Write-Output "Frontend port 3000 is already in use; leaving its process untouched."
} else {
    $frontendCommand = "Set-Location -LiteralPath '$frontendDirectory'; npm run dev"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-Command", $frontendCommand) `
        -WorkingDirectory $frontendDirectory
    Write-Output "Started frontend at http://localhost:3000"
}

Write-Output "Start Wokwi separately from the VS Code Wokwi extension when ready."