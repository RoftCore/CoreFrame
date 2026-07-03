using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

static class Program
{
    static NotifyIcon trayIcon;
    static Form form;
    static Process process;
    static string sigFile;
    static Mutex mutex;

    [STAThread]
    static void Main()
    {
        bool createdNew;
        mutex = new Mutex(false, "CoreFrameControllerMutex", out createdNew);
        sigFile = Path.Combine(Application.StartupPath, ".show");

        if (!createdNew)
        {
            try { File.WriteAllText(sigFile, "1"); } catch { }
            mutex.Dispose();
            return;
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        string batPath = Path.Combine(Application.StartupPath, "run.bat");
        process = new Process();
        process.StartInfo.FileName = batPath;
        process.StartInfo.UseShellExecute = false;
        process.StartInfo.CreateNoWindow = true;
        process.StartInfo.WindowStyle = ProcessWindowStyle.Hidden;
        process.Start();

        form = new Form();
        form.Text = "CoreFrame";
        form.Size = new System.Drawing.Size(320, 140);
        form.StartPosition = FormStartPosition.CenterScreen;
        form.FormBorderStyle = FormBorderStyle.FixedSingle;
        form.MaximizeBox = false;
        form.TopMost = true;
        form.FormClosing += (s, e) =>
        {
            if (e.CloseReason == CloseReason.ApplicationExitCall) return;
            e.Cancel = true;
            form.Hide();
        };

        trayIcon = new NotifyIcon();
        trayIcon.Text = "CoreFrame";
        trayIcon.Icon = System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        trayIcon.Visible = true;

        var trayMenu = new ContextMenuStrip();
        trayMenu.Items.Add("Show", null, (s, e) => { form.Show(); form.WindowState = FormWindowState.Normal; form.BringToFront(); });
        trayMenu.Items.Add("Stop", null, (s, e) => StopCoreFrame());
        trayMenu.Items.Add("Exit", null, (s, e) => StopCoreFrame());
        trayIcon.ContextMenuStrip = trayMenu;

        trayIcon.DoubleClick += (s, e) => { form.Show(); form.WindowState = FormWindowState.Normal; form.BringToFront(); };

        var showTimer = new System.Windows.Forms.Timer();
        showTimer.Interval = 500;
        showTimer.Tick += (s, e) =>
        {
            if (File.Exists(sigFile))
            {
                try { File.Delete(sigFile); } catch { }
                form.Show();
                form.WindowState = FormWindowState.Normal;
                form.BringToFront();
            }
        };
        showTimer.Start();

        var stopBtn = new Button();
        stopBtn.Text = "Stop";
        stopBtn.Size = new System.Drawing.Size(120, 35);
        stopBtn.Location = new System.Drawing.Point(15, 15);
        stopBtn.Click += (s, e) => StopCoreFrame();

        var hideBtn = new Button();
        hideBtn.Text = "Hide to tray";
        hideBtn.Size = new System.Drawing.Size(120, 35);
        hideBtn.Location = new System.Drawing.Point(150, 15);
        hideBtn.Click += (s, e) => form.Hide();

        var statusLabel = new Label();
        statusLabel.Text = "PID: " + process.Id + " - Running";
        statusLabel.Location = new System.Drawing.Point(15, 65);
        statusLabel.Size = new System.Drawing.Size(280, 20);

        var infoLabel = new Label();
        infoLabel.Text = "Close = hides to tray (use tray or button to stop)";
        infoLabel.ForeColor = System.Drawing.Color.Gray;
        infoLabel.Location = new System.Drawing.Point(15, 90);
        infoLabel.Size = new System.Drawing.Size(280, 20);

        form.Controls.AddRange(new Control[] { stopBtn, hideBtn, statusLabel, infoLabel });

        form.FormClosed += (s, e) =>
        {
            try { File.Delete(sigFile); } catch { }
            showTimer.Stop();
            showTimer.Dispose();
            mutex.ReleaseMutex();
            mutex.Dispose();
            trayIcon.Visible = false;
            trayIcon.Dispose();
        };

        Application.Run(form);
    }

    static void StopCoreFrame()
    {
        try
        {
            var req = System.Net.WebRequest.CreateHttp("http://127.0.0.1:5000/api/quit");
            req.Method = "POST";
            req.Timeout = 3000;
            try { req.GetResponse().Close(); } catch { }
        }
        catch { }
        Thread.Sleep(500);
        if (process != null && !process.HasExited)
        {
            KillProcessTree(process.Id);
        }
        trayIcon.Visible = false;
        Application.Exit();
    }

    static void KillProcessTree(int pid)
    {
        try
        {
            var searcher = new System.Management.ManagementObjectSearcher(
                "SELECT ProcessId FROM Win32_Process WHERE ParentProcessId=" + pid);
            foreach (var obj in searcher.Get())
            {
                int childPid = Convert.ToInt32(obj["ProcessId"]);
                KillProcessTree(childPid);
            }
        }
        catch { }
        try
        {
            var p = Process.GetProcessById(pid);
            p.Kill();
        }
        catch { }
    }
}
