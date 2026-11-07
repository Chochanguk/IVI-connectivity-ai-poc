$projectRoot = Split-Path $PSScriptRoot -Parent
$dhu = Join-Path $env:LOCALAPPDATA 'Android\Sdk\extras\google\auto\desktop-head-unit.exe'
$commandFile = Join-Path $PSScriptRoot 'tc03-focus.dhu'
$stdoutFile = Join-Path $projectRoot 'results\logs\tc03-dhu-output.txt'
$stderrFile = Join-Path $projectRoot 'results\logs\tc03-dhu-error.txt'
if (-not (Test-Path -LiteralPath $dhu)) { throw "DHU not found: $dhu" }
New-Item -ItemType Directory -Path (Split-Path $stdoutFile) -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'results\screenshots') -Force | Out-Null
$dhuProcess = Start-Process -FilePath $dhu -WorkingDirectory $projectRoot -RedirectStandardInput $commandFile -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -WindowStyle Normal -Wait -PassThru
Write-Output "DHU exit code: $($dhuProcess.ExitCode)"
Write-Output "DHU console output: $stdoutFile"
