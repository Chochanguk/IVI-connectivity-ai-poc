param([Parameter(Mandatory=$true)][string]$OutputFile)
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
if (-not (Test-Path -LiteralPath $adb)) { throw "ADB not found: $adb" }
Write-Host 'Ctrl+C로 중지합니다. 원본 Logcat에 민감정보가 포함될 수 있습니다.'
& $adb logcat -v threadtime -T 1 | Out-File -LiteralPath $OutputFile -Encoding utf8
