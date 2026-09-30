param([int]$Port = 8000, [switch]$ShareOnNetwork)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$quizPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $quizPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
    & $quizPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$quizAddress = if ($ShareOnNetwork) { '0.0.0.0' } else { '127.0.0.1' }
Write-Host "Open http://localhost:$Port in your browser. Keep this window running."
& $quizPython -m uvicorn web_app:app --host $quizAddress --port $Port --workers 1
