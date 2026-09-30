param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$quizPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $quizPython)) {
    throw 'Run start-web.ps1 once to install the application dependencies.'
}
$quizListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($quizListener) {
    $quizExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $($quizListener[0].OwningProcess)"
    if ($quizExisting.CommandLine -notmatch 'uvicorn web_app:app') {
        throw "Port $Port is already in use by another application."
    }
    if ($quizListener.LocalAddress -contains '127.0.0.1') {
        throw 'The local-only server is still running. Stop that server before starting company access.'
    }
    Write-Host 'The company education server is already running.'
} else {
    $quizLogs = Join-Path $PSScriptRoot 'artifacts'
    New-Item -ItemType Directory -Path $quizLogs -Force | Out-Null
    Start-Process -FilePath $quizPython -ArgumentList @('-m','uvicorn','web_app:app','--host','0.0.0.0','--port',"$Port",'--workers','1') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $quizLogs 'company-server-output.log') -RedirectStandardError (Join-Path $quizLogs 'company-server-error.log') | Out-Null
    $quizReady = $false
    for ($quizTry = 0; $quizTry -lt 30; $quizTry++) {
        Start-Sleep -Milliseconds 500
        try {
            $quizResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2
            if ($quizResponse.StatusCode -eq 200) { $quizReady = $true; break }
        } catch {}
    }
    if (-not $quizReady) { throw 'Server did not start. Check artifacts/company-server-error.log.' }
    Write-Host 'Company education server started in the background.'
}
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | ForEach-Object {
    foreach ($quizIp in $_.IPv4Address.IPAddress) { Write-Host "Employee address: http://${quizIp}:$Port" }
}
Write-Host 'Keep this PC switched on and awake while employees use the site.'
