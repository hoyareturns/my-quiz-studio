param([string]$Domain = 'valley-unfrozen-chalice.ngrok-free.dev')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($Domain -notmatch '^[a-z0-9-]+\.ngrok-free\.(dev|app)$') { throw 'Use the account-assigned ngrok free domain.' }
$quizAgentDir = Join-Path $PSScriptRoot '.cache\ngrok'
$quizAgentExe = Join-Path $quizAgentDir 'ngrok.exe'
$quizAgentConfig = Join-Path $quizAgentDir 'agent.yml'
foreach ($quizFile in @($quizAgentExe,$quizAgentConfig)) {
    if (-not (Test-Path -LiteralPath $quizFile)) { throw 'External connection setup is incomplete. The local ngrok agent and account configuration are required.' }
}
& $quizAgentExe config check --config $quizAgentConfig
if ($LASTEXITCODE -ne 0) { throw 'Invalid ngrok connection configuration.' }
& (Join-Path $PSScriptRoot 'start-company-server.ps1')
# Keep authoring and administration protected while learning sections stay public.
$quizBootstrap = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/bootstrap' -TimeoutSec 30
if ($quizBootstrap.authoring_private -ne $true) { throw 'Update/restart the education server before enabling public learning.' }
foreach ($quizPrivatePath in @('admin/settings','admin/backups','author/template','participation')) {
    try {
        $quizProbe = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/$quizPrivatePath" -UseBasicParsing -TimeoutSec 5
        $quizStatus = [int]$quizProbe.StatusCode
    } catch {
        if (-not $_.Exception.Response) { throw }
        $quizStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($quizStatus -ne 401) { throw "Administrator protection check failed: $quizPrivatePath" }
}
try {
    $quizExistingTunnels = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
    if (@($quizExistingTunnels.tunnels | Where-Object {$_.public_url -eq "https://$Domain"}).Count -gt 0) {
        Write-Host "External connection is already running: https://$Domain"
        return
    }
    if ($quizExistingTunnels.tunnels) { throw 'An ngrok tunnel is already running. Inspect it before starting another one.' }
} catch {
    if ($_.Exception.Message -like 'An ngrok tunnel*') { throw }
}
$quizLog = Join-Path $PSScriptRoot 'artifacts\ngrok.log'
$quizPendingAgent = Get-CimInstance Win32_Process -Filter "Name = 'ngrok.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($quizAgentConfig)
}
if ($quizPendingAgent) { throw 'The existing ngrok agent is still connecting. Retry after the network is ready.' }
$quizArgs = 'http http://127.0.0.1:8000 --url="https://' + $Domain + '" --config="' + $quizAgentConfig + '" --inspect=false --log="' + $quizLog + '" --log-format=json'
Start-Process -FilePath $quizAgentExe -ArgumentList $quizArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null
$quizConnected = $false
for ($quizTry = 0; $quizTry -lt 30; $quizTry++) {
    Start-Sleep -Milliseconds 500
    try {
        $quizTunnels = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
        if (@($quizTunnels.tunnels | Where-Object {$_.public_url -eq "https://$Domain"}).Count -gt 0) { $quizConnected = $true; break }
    } catch {}
}
if (-not $quizConnected) { throw 'External connection did not start. Check artifacts/ngrok.log.' }
Write-Host "External URL: https://$Domain"
Write-Host 'Learning sections are public. Authoring and administration require administrator login.'
