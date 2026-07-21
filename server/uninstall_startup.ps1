# uninstall_startup.ps1
# Removes the Bifrost Startup shortcut created by install_startup.ps1.
#
# Usage: pwsh .\uninstall_startup.ps1

$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir 'Bifrost.lnk'

if (Test-Path $ShortcutPath) {
    Remove-Item -Force $ShortcutPath
    Write-Host "[OK] Removed startup shortcut: $ShortcutPath"
} else {
    Write-Host "[INFO] No startup shortcut found - nothing to do."
}
