param([switch]$Remove)

$taskName = "CoreFrame"
$psScript = "E:\Programming\CoreFrame\controller.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$psScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[*] Tarea '$taskName' eliminada."
    return
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force

# Quitar entrada antigua de Startup Folder (si existe)
$startupPath = [Environment]::GetFolderPath("Startup")
$oldLinks = Get-ChildItem "$startupPath\*CoreFrame*" -ErrorAction SilentlyContinue
foreach ($link in $oldLinks) { Remove-Item $link -Force }

Write-Host "[OK] Tarea '$taskName' creada — CoreFrame arrancará al iniciar sesión sin UAC."
Write-Host "     Para desinstalar: .\setup-autostart.ps1 -Remove"
