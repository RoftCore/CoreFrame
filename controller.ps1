Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Stop-ProcessTree {
    param([int]$ParentId)
    $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ParentId }
    foreach ($child in $children) { Stop-ProcessTree $child.ProcessId }
    Get-Process -Id $ParentId -ErrorAction SilentlyContinue | Stop-Process -Force
}

function Stop-CoreFrame {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/quit" -Method Post -TimeoutSec 3 -ErrorAction SilentlyContinue } catch {}
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) { $trayIcon.Visible = $false; [System.Windows.Forms.Application]::Exit(); return }
    Stop-ProcessTree $process.Id
    $trayIcon.Visible = $false
    [System.Windows.Forms.Application]::Exit()
}

$createdNew = $false
$mutex = $null
try {
    $mutex = New-Object System.Threading.Mutex($false, "CoreFrameControllerMutex", [ref]$createdNew)
} catch {}

$sigFile = Join-Path $PSScriptRoot ".show"

if (-not $createdNew -and $mutex -ne $null) {
    try { "1" | Set-Content $sigFile -Force } catch {}
    $mutex.Dispose()
    exit
}

$batPath = Join-Path $PSScriptRoot "run.bat"
$process = Start-Process -FilePath $batPath -WindowStyle Hidden -PassThru

$form = New-Object System.Windows.Forms.Form
$form.Text = "CoreFrame"
$form.Size = New-Object System.Drawing.Size(320, 160)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false
$form.TopMost = $true

$trayIcon = New-Object System.Windows.Forms.NotifyIcon
$trayIcon.Text = "CoreFrame"
$trayIcon.Icon = [System.Drawing.Icon]::new((Join-Path $PSScriptRoot "CoreFrame.ico"))
$trayIcon.Visible = $true

$trayMenu = New-Object System.Windows.Forms.ContextMenuStrip
$showItem = New-Object System.Windows.Forms.ToolStripMenuItem("Show")
$showItem.Add_Click({ $form.Show(); $form.WindowState = "Normal"; $form.BringToFront() })
$stopItem = New-Object System.Windows.Forms.ToolStripMenuItem("Stop")
$stopItem.Add_Click({ Stop-CoreFrame })
$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem("Exit")
$exitItem.Add_Click({ Stop-CoreFrame })
$trayMenu.Items.AddRange(@($showItem, $stopItem, $exitItem))
$trayIcon.ContextMenuStrip = $trayMenu

$trayIcon.Add_DoubleClick({
    $form.Show()
    $form.WindowState = "Normal"
    $form.BringToFront()
})

$showTimer = New-Object System.Windows.Forms.Timer
$showTimer.Interval = 500
$showTimer.Add_Tick({
    if (Test-Path $sigFile) {
        Remove-Item $sigFile -Force -ErrorAction SilentlyContinue
        $form.Show()
        $form.WindowState = "Normal"
        $form.BringToFront()
    }
})
$showTimer.Start()

$form.Add_FormClosing({
    param($sender, $e)
    if ($e.CloseReason -ne "ApplicationExitCall") {
        $e.Cancel = $true
        $form.Hide()
    }
})

$stopBtn = New-Object System.Windows.Forms.Button
$stopBtn.Text = "Stop"
$stopBtn.Size = New-Object System.Drawing.Size(120, 35)
$stopBtn.Location = New-Object System.Drawing.Point(15, 15)
$stopBtn.Add_Click({ Stop-CoreFrame })

$hideBtn = New-Object System.Windows.Forms.Button
$hideBtn.Text = "Hide to tray"
$hideBtn.Size = New-Object System.Drawing.Size(120, 35)
$hideBtn.Location = New-Object System.Drawing.Point(150, 15)
$hideBtn.Add_Click({ $form.Hide() })

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "PID: $($process.Id) - Running"
$statusLabel.Location = New-Object System.Drawing.Point(15, 65)
$statusLabel.Size = New-Object System.Drawing.Size(280, 20)

$infoLabel = New-Object System.Windows.Forms.Label
$infoLabel.Text = "Close = hides to tray (use tray or button to stop)"
$infoLabel.ForeColor = [System.Drawing.Color]::Gray
$infoLabel.Location = New-Object System.Drawing.Point(15, 90)
$infoLabel.Size = New-Object System.Drawing.Size(280, 20)

$form.Controls.AddRange(@($stopBtn, $hideBtn, $statusLabel, $infoLabel))

$form.Add_FormClosed({
    try { Remove-Item $sigFile -Force -ErrorAction SilentlyContinue } catch {}
    try { $showTimer.Stop(); $showTimer.Dispose() } catch {}
    try { $mutex.ReleaseMutex(); $mutex.Dispose() } catch {}
    $trayIcon.Visible = $false
    $trayIcon.Dispose()
})

[System.Windows.Forms.Application]::Run($form)
