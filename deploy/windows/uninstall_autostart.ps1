# Melepas pintasan "DEPRO Gerbang" dari folder Startup pengguna (lihat install_autostart.ps1).
$link = Join-Path ([Environment]::GetFolderPath("Startup")) "DEPRO Gerbang.lnk"
if (Test-Path $link) { Remove-Item $link -Force; Write-Output "Dilepas: $link" } else { Write-Output "Tidak terpasang." }
