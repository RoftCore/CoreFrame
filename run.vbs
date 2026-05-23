Set Shell = CreateObject("Shell.Application")
Set WShell = CreateObject("WScript.Shell")

' Self-elevate so sc/netsh/taskkill work on system services
IsAdmin = WShell.Run("powershell.exe -Command ""exit (1 - [int][Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))""", 0, True)
If IsAdmin <> 0 Then
    Shell.ShellExecute "wscript.exe", """" & WScript.ScriptFullName & """", "", "runas", 0
    WScript.Quit
End If

WShell.Run "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File E:\Programming\CoreFrame\controller.ps1", 0, False
