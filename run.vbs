Set Shell = CreateObject("Shell.Application")
Set WShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
exePath = scriptDir & "\CoreFrameTray.exe"

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ""exit (1 - [int][Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"""
IsAdmin = WShell.Run(cmd, 0, True)
If IsAdmin <> 0 Then
    Shell.ShellExecute exePath, "", "", "runas", 0
Else
    WShell.Run """" & exePath & """", 0, False
End If
