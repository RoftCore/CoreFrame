// CoreFrame launcher stub. One .exe that deploys the host once and then is a shortcut.
//
// First launch: unpacks the embedded host.zip into DATA_DIR\bin\host, writes
// host.stamp, then starts bin\host\CoreFrame.exe. Later launches: the stamp
// matches, nothing is unpacked, the host is spawned directly. Same contract as
// runner.zip in coreframe/host/boot.py (pitfall 62).
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CoreFrameStub
{
    internal static class Program
    {
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr FindWindowW(string className, string windowName);

        private const string WindowTitle = "CoreFrame";
        private const int SplashTimeoutMs = 45000;

        private static string HostDir()
        {
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            return Path.Combine(Path.Combine(docs, "CoreFrame"), Path.Combine("bin", "host"));
        }

        private static bool IsDeployed(string hostExe, string stampFile)
        {
            try
            {
                if (!File.Exists(hostExe) || !File.Exists(stampFile)) return false;
                return File.ReadAllText(stampFile).Trim() == StubInfo.Stamp;
            }
            catch (Exception)
            {
                return false;
            }
        }

        [STAThread]
        private static int Main(string[] argv)
        {
            string hostDir = HostDir();
            string hostExe = Path.Combine(hostDir, "CoreFrame.exe");
            string stampFile = Path.Combine(hostDir, "host.stamp");
            bool deployed = IsDeployed(hostExe, stampFile);

            SplashForm splash = new SplashForm();
            splash.Show();
            splash.SetStatus(deployed ? "Starting CoreFrame..." : "Installing CoreFrame...");
            Application.DoEvents();

            if (!deployed)
            {
                try
                {
                    Deploy(hostDir, splash);
                }
                catch (Exception ex)
                {
                    splash.Close();
                    MessageBox.Show("CoreFrame could not be installed:\n\n" + ex.Message,
                        "CoreFrame", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return 2;
                }
            }

            Process host;
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(hostExe);
                psi.WorkingDirectory = hostDir;
                psi.UseShellExecute = false;
                if (argv != null && argv.Length > 0) psi.Arguments = JoinArgs(argv);
                host = Process.Start(psi);
            }
            catch (Exception ex)
            {
                splash.Close();
                MessageBox.Show("CoreFrame could not start:\n\n" + ex.Message + "\n\n" + hostExe,
                    "CoreFrame", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 3;
            }

            splash.WaitForHost(host, SplashTimeoutMs);
            return 0;
        }

        private static string JoinArgs(string[] argv)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < argv.Length; i++)
            {
                if (i > 0) sb.Append(' ');
                if (argv[i].IndexOf(' ') >= 0) sb.Append('"').Append(argv[i]).Append('"');
                else sb.Append(argv[i]);
            }
            return sb.ToString();
        }

        // Deploy next to the target and swap, so a half-written tree is never spawned.
        private static void Deploy(string hostDir, SplashForm splash)
        {
            string tmp = hostDir + ".new";
            string old = hostDir + ".old";
            string tmpStamp = Path.Combine(tmp, "host.stamp");
            TryDelete(old);

            // A tree extracted by an earlier attempt is reused: an update started while
            // the host is running used to re-extract 52 MB on every launch.
            bool staged = false;
            try
            {
                staged = Directory.Exists(tmp) && File.Exists(tmpStamp)
                         && File.ReadAllText(tmpStamp).Trim() == StubInfo.Stamp
                         && File.Exists(Path.Combine(tmp, "CoreFrame.exe"));
            }
            catch (Exception)
            {
                staged = false;
            }

            if (!staged)
            {
                TryDelete(tmp);
                Directory.CreateDirectory(tmp);
                Extract(tmp, splash);
                File.WriteAllText(tmpStamp, StubInfo.Stamp);
            }
            else
            {
                splash.SetStatus("Installing CoreFrame...");
            }

            bool movedAway = false;
            if (Directory.Exists(hostDir))
            {
                try
                {
                    Directory.Move(hostDir, old);
                    movedAway = true;
                }
                catch (Exception)
                {
                    // The host is running from it: the staged tree stays for the next launch.
                }
            }

            if (Directory.Exists(hostDir))
            {
                return;
            }

            try
            {
                Directory.Move(tmp, hostDir);
            }
            catch (Exception)
            {
                if (movedAway)
                {
                    try { Directory.Move(old, hostDir); } catch (Exception) { }
                }
                throw;
            }

            File.WriteAllText(Path.Combine(hostDir, "host.stamp"), StubInfo.Stamp);
            File.WriteAllText(Path.Combine(hostDir, "host.version"), StubInfo.Version);
            if (movedAway) TryDelete(old);
        }

        private static void Extract(string tmp, SplashForm splash)
        {
            Assembly self = Assembly.GetExecutingAssembly();
            using (Stream payload = self.GetManifestResourceStream(StubInfo.Payload))
            {
                if (payload == null) throw new InvalidOperationException("payload missing from the executable");
                using (ZipArchive zip = new ZipArchive(payload, ZipArchiveMode.Read))
                {
                    int n = 0;
                    foreach (ZipArchiveEntry entry in zip.Entries)
                    {
                        string target = Path.Combine(tmp, entry.FullName.Replace('/', Path.DirectorySeparatorChar));
                        if (entry.Name.Length == 0)
                        {
                            Directory.CreateDirectory(target);
                            continue;
                        }
                        string dir = Path.GetDirectoryName(target);
                        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                        entry.ExtractToFile(target, true);
                        n++;
                        if ((n % 250) == 0)
                        {
                            splash.SetStatus("Installing CoreFrame... " + n + " files");
                            Application.DoEvents();
                        }
                    }
                }
            }
        }

        private static void TryDelete(string dir)
        {
            try
            {
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
            }
            catch (Exception)
            {
            }
        }

        internal sealed class SplashForm : Form
        {
            private readonly Label _status;
            private readonly Image _image;

            public SplashForm()
            {
                FormBorderStyle = FormBorderStyle.None;
                StartPosition = FormStartPosition.CenterScreen;
                ShowInTaskbar = false;
                BackColor = Color.FromArgb(13, 13, 26);
                ClientSize = new Size(440, 330);

                _image = LoadImage();
                if (_image != null)
                {
                    ClientSize = new Size(_image.Width, _image.Height);
                    PictureBox pic = new PictureBox();
                    pic.Image = _image;
                    pic.Dock = DockStyle.Fill;
                    pic.SizeMode = PictureBoxSizeMode.Normal;
                    Controls.Add(pic);
                }

                _status = new Label();
                _status.AutoSize = false;
                _status.TextAlign = ContentAlignment.MiddleLeft;
                _status.ForeColor = Color.FromArgb(160, 160, 176);
                _status.BackColor = Color.Transparent;
                _status.Font = new Font("Segoe UI", 9f);
                _status.Bounds = new Rectangle(24, ClientSize.Height - 42, ClientSize.Width - 48, 20);
                _status.Text = "Starting...";
                Controls.Add(_status);
                _status.BringToFront();
            }

            private static Image LoadImage()
            {
                try
                {
                    Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(StubInfo.Splash);
                    if (s == null) return null;
                    return Image.FromStream(s);
                }
                catch (Exception)
                {
                    return null;
                }
            }

            public void SetStatus(string text)
            {
                try
                {
                    _status.Text = text;
                    Update();
                }
                catch (Exception)
                {
                }
            }

            public void WaitForHost(Process host, int timeoutMs)
            {
                Stopwatch sw = Stopwatch.StartNew();
                IntPtr hwnd = IntPtr.Zero;
                while (sw.ElapsedMilliseconds < timeoutMs)
                {
                    try
                    {
                        Application.DoEvents();
                        if (host != null && host.HasExited) break;
                        if (hwnd == IntPtr.Zero) hwnd = FindWindowW(null, WindowTitle);
                        if (hwnd != IntPtr.Zero && sw.ElapsedMilliseconds > 700) break;
                    }
                    catch (Exception)
                    {
                    }
                    Thread.Sleep(60);
                }
                try { Close(); } catch (Exception) { }
            }

            protected override void Dispose(bool disposing)
            {
                if (disposing && _image != null) _image.Dispose();
                base.Dispose(disposing);
            }
        }
    }
}
