# DEPRO (T29): server gerbang menyala sendiri saat pengguna Windows login.
# Membuat pintasan "DEPRO Gerbang" di folder Startup pengguna ini (tanpa hak admin),
# sama seperti cara Ollama menyala otomatis. start_system.bat memakai penjaga proses
# (python -m backend.supervisor) sehingga server dinyalakan ulang bila crash.
#
# Pakai (dari akar repo):   powershell -ExecutionPolicy Bypass -File deploy\windows\install_autostart.ps1
# Lepas:                    powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall_autostart.ps1
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$target = Join-Path $repo "start_system.bat"
if (-not (Test-Path $target)) { throw "start_system.bat tidak ditemukan di $repo" }
$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "DEPRO Gerbang.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $repo
$shortcut.WindowStyle = 7          # jendela terminal diminimalkan, tetap bisa dibuka untuk Ctrl+C
$shortcut.Description = "DEPRO - server gerbang APD (menyala saat login)"
$shortcut.Save()
Write-Output "Terpasang: $link -> $target"
Write-Output "Pastikan backend\.env berisi CAMERA_AUTOSTART=true dan CAMERA_NAME=<nama kamera eksternal>."
