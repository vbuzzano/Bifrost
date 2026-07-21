' Launches start_bifrost.bat with a fully hidden window (0 = SW_HIDE).
' A .bat run directly always flashes a cmd.exe window, even minimized -
' this is the standard workaround. Used by the Startup shortcut instead
' of pointing it at the .bat directly.
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """" & ScriptDir & "\start_bifrost.bat""", 0, False
