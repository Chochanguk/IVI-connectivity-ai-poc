$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$adb = Join-Path $sdk 'platform-tools\adb.exe'
$dhu = Join-Path $sdk 'extras\google\auto\desktop-head-unit.exe'
if (-not (Test-Path -LiteralPath $adb) -or -not (Test-Path -LiteralPath $dhu)) { throw 'ADB or DHU not installed.' }
& $adb forward tcp:5277 tcp:5277
& $dhu
