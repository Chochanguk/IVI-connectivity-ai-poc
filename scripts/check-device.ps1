$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
if (-not (Test-Path -LiteralPath $adb)) { throw "ADB not found: $adb" }
& $adb devices
& $adb shell getprop ro.product.model
& $adb shell getprop ro.build.version.release
