$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$quizLogDirectory = Join-Path $PSScriptRoot 'artifacts'
New-Item -ItemType Directory -Path $quizLogDirectory -Force | Out-Null
$quizStartupLog = Join-Path $quizLogDirectory 'automatic-start.log'
Add-Content -LiteralPath $quizStartupLog -Encoding UTF8 -Value "$(Get-Date -Format s) Automatic startup requested."

# Networking may become available after Windows finishes signing in.
for ($quizStartupTry = 1; $quizStartupTry -le 5; $quizStartupTry++) {
    try {
        & (Join-Path $PSScriptRoot 'start-external-access.ps1') *>&1 | Out-File -LiteralPath $quizStartupLog -Encoding UTF8 -Append
        Add-Content -LiteralPath $quizStartupLog -Encoding UTF8 -Value "$(Get-Date -Format s) Automatic startup completed."
        exit 0
    } catch {
        Add-Content -LiteralPath $quizStartupLog -Encoding UTF8 -Value "$(Get-Date -Format s) Attempt $quizStartupTry failed: $($_.Exception.Message)"
        if ($quizStartupTry -lt 5) { Start-Sleep -Seconds 30 }
    }
}
Add-Content -LiteralPath $quizStartupLog -Encoding UTF8 -Value "$(Get-Date -Format s) Startup failed. Run the external-access launcher after checking the network."
exit 1
