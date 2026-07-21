# install_startup.ps1
# Adds Bifrost to the current user's Startup folder so it launches
# automatically at login. Run once from wherever you extracted the
# release zip - the shortcut points back to this exact folder.
#
# Usage: pwsh .\install_startup.ps1

$ServerDir = $PSScriptRoot
$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir 'Bifrost.lnk'

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
# Target wscript.exe running start_bifrost.vbs (not the .bat directly) -
# a .bat always flashes a visible cmd.exe window on launch, even with
# WindowStyle set to minimized on the shortcut. The .vbs launches the
# .bat with a fully hidden window instead.
$Shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$Shortcut.Arguments = '"' + (Join-Path $ServerDir 'start_bifrost.vbs') + '"'
$Shortcut.WorkingDirectory = $ServerDir
$Shortcut.Description = 'Bifrost - Amiga mouse/keyboard server'
$Shortcut.Save()

Write-Host "[OK] Bifrost will start automatically at next login."
Write-Host "     Shortcut: $ShortcutPath"
Write-Host "     Logs:     $ServerDir\bifrost.log"
Write-Host "     To disable: run uninstall_startup.ps1 (or delete the shortcut above)."
