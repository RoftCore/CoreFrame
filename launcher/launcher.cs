// CoreFrame launcher stub — distribucion en un solo fichero.
//
// Que hace:
//   1. Lee su propio binario y localiza el paquete pegado al final.
//   2. Compara la firma del paquete con el fichero host.stamp de la carpeta destino.
//      Si coincide y el host ya esta, no toca nada (arranque rapido).
//   3. Si no coincide (primera ejecucion o build nuevo): extrae el paquete a
//      <destino>.new, aparta el anterior como <destino>.old, renombra el nuevo y
//      escribe la firma. Luego lanza el host.
//
// Disposicion del fichero (el "trailer" van al FINAL para leerlo sin recorrer 51 MB):
//   [ codigo del stub ][ payload (zip) ][ Int64 longitud ][ 16 bytes sha256 ][ MARKER 16 ]
//
// Se compila con el csc de .NET Framework 4 (C# 5: sin interpolacion, sin ?., sin =>).
//   csc /nologo /target:winexe /optimize+ /out:CoreFrameStub.exe *.cs
// Para escribir C# 5-compatible: prohibido $"", ?., ??=, => en propiedades.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Threading;
using System.Windows.Forms;

static class CoreFrameStub
{
    // Firma de 16 bytes que separa el codigo del paquete. Debe coincidir con el
    // script de empaquetado (build-setup.ps1) caracter a caracter.
    static readonly byte[] MARKER = new byte[] {
        0xC0, 0xFF, 0xEE, 0x11, 0x22, 0x33, 0x44, 0x55,
        0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD };

    // trailer = 8 (longitud) + 16 (hash) + 16 (marker)
    const int TRAILER = 40;
    const int OFF_LENGTH = 0;
    const int OFF_HASH = 8;
    const int OFF_MARKER = 24;

    // Argumentos que consume el stub; el resto se pasan tal cual al host.
    static int Main(string[] args)
    {
        string installDir = null;
        bool noLaunch = false;
        List<string> pass = new List<string>();

        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--install-dir" && i + 1 < args.Length)
            {
                installDir = args[i + 1];
                i++;
            }
            else if (args[i] == "--no-launch")
            {
                noLaunch = true;
            }
            else
            {
                pass.Add(args[i]);
            }
        }

        try
        {
            string self = Process.GetCurrentProcess().MainModule.FileName;

            long fileLen;
            long payloadLen;
            byte[] payloadHash = new byte[16];

            using (FileStream fs = File.OpenRead(self))
            {
                fileLen = fs.Length;
                if (fileLen < TRAILER)
                {
                    return Fail("Este ejecutable no lleva el paquete de CoreFrame dentro.\n\n"
                        + "Descarga de nuevo CoreFrame-Setup.exe completo.");
                }

                byte[] trailer = new byte[TRAILER];
                fs.Seek(fileLen - TRAILER, SeekOrigin.Begin);
                if (ReadFull(fs, trailer, TRAILER) != TRAILER)
                {
                    return Fail("No se pudo leer la cabecera del paquete.");
                }

                for (int i = 0; i < 16; i++)
                {
                    if (trailer[OFF_MARKER + i] != MARKER[i])
                    {
                        return Fail("La firma del paquete no es valida (fichero danado o modificado).");
                    }
                }

                payloadLen = BitConverter.ToInt64(trailer, OFF_LENGTH);
                Array.Copy(trailer, OFF_HASH, payloadHash, 0, 16);

                if (payloadLen <= 0 || payloadLen > fileLen - TRAILER)
                {
                    return Fail("El tamano del paquete no cuadra.");
                }
            }

            long payloadOffset = fileLen - TRAILER - payloadLen;

            // Destino por defecto: <Documentos>\CoreFrame\bin\host  (SpecialFolder.Personal
            // respeta la redireccion de Documentos; el host y su _internal van juntos).
            string hostDir = installDir;
            if (hostDir == null)
            {
                hostDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Personal),
                                       Path.Combine("CoreFrame", Path.Combine("bin", "host")));
            }
            string hostExe = Path.Combine(hostDir, "CoreFrame.exe");
            string stampPath = Path.Combine(Path.GetDirectoryName(hostDir), "host.stamp");
            string want = Hex(payloadHash) + " " + payloadLen.ToString();

            // Limpieza oportunista de un .old que no se pudo borrar en el arranque anterior.
            string hostOld = hostDir + ".old";
            if (Directory.Exists(hostOld))
            {
                TryDeleteDir(hostOld);
            }

            bool alreadyThere = File.Exists(hostExe)
                                && File.Exists(stampPath)
                                && File.ReadAllText(stampPath).Trim() == want;

            if (!alreadyThere)
            {
                string error = Install(self, payloadOffset, payloadLen, hostDir, stampPath, want);
                if (error != null)
                {
                    // Si el motivo es que el host esta en uso, seguimos con el que ya hay:
                    // el reemplazo se reintenta en el proximo arranque (no escribimos stamp).
                    if (!(error == "INUSE" && File.Exists(hostExe)))
                    {
                        return Fail(error);
                    }
                    if (!noLaunch)
                    {
                        MessageBox.Show("CoreFrame esta abierto, asi que no se puede reemplazar ahora.\n\n"
                            + "La version nueva se aplicara en el proximo arranque.",
                            "CoreFrame", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }
                }
            }

            if (noLaunch)
            {
                return 0;
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = hostExe;
            psi.Arguments = JoinArgs(pass);
            psi.WorkingDirectory = hostDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            return Fail(ex.Message);
        }
    }

    // Extrae el paquete y lo instala. Devuelve null si todo fue bien, "INUSE" si no se
    // pudo reemplazar porque el host estaba corriendo, o el mensaje de error.
    static string Install(string self, long payloadOffset, long payloadLen, string hostDir, string stampPath, string want)
    {
        string parent = Path.GetDirectoryName(hostDir);
        string hostNew = hostDir + ".new";
        string hostOld = hostDir + ".old";
        string tmpZip = Path.Combine(Path.GetTempPath(), "coreframe-payload-" + Guid.NewGuid().ToString("N") + ".zip");

        string error = null;

        Thread worker = new Thread(delegate()
        {
            try
            {
                // Si el host esta corriendo, su .exe esta mapeado y no se puede reemplazar.
                // Comprobarlo ANTES de extraer evita escribir 82 MB para nada y, sobre todo,
                // evita renombrar la carpeta de una aplicacion viva (mezclaria versiones).
                if (!IsReplaceable(hostDir))
                {
                    error = "INUSE";
                    return;
                }

                if (!Directory.Exists(parent))
                {
                    Directory.CreateDirectory(parent);
                }
                TryDeleteDir(hostNew);
                TryDeleteDir(hostOld);

                // 1. Sacar el zip del propio exe a un fichero temporal (ZipFile necesita
                //    un stream que empiece en el zip, y el nuestro empieza a mitad del exe).
                CopyRange(self, payloadOffset, payloadLen, tmpZip);

                // 2. Descomprimir en <destino>.new
                if (!Directory.Exists(hostNew))
                {
                    Directory.CreateDirectory(hostNew);
                }
                ZipFile.ExtractToDirectory(tmpZip, hostNew);

                // 3. Cambio por renombrado: nada se pierde hasta que el nuevo esta en su sitio.
                if (Directory.Exists(hostDir))
                {
                    try
                    {
                        Directory.Move(hostDir, hostOld);
                    }
                    catch (Exception)
                    {
                        TryDeleteDir(hostNew);
                        error = "INUSE";
                        return;
                    }
                }
                Directory.Move(hostNew, hostDir);
                if (!TryDeleteDir(hostOld))
                {
                    // Se queda como .old y el proximo arranque lo borra.
                }

                // 4. Firma: a partir de ahora el arranque es directo.
                File.WriteAllText(stampPath, want);
            }
            catch (Exception ex)
            {
                error = ex.Message;
            }
            finally
            {
                TryDeleteFile(tmpZip);
            }
        });

        worker.IsBackground = true;
        worker.Start();

        // Ventana de progreso solo si la extraccion tarda (primera ejecucion: unos segundos).
        Form form = MakeForm(hostDir);
        Stopwatch sw = Stopwatch.StartNew();
        bool shown = false;
        while (worker.IsAlive)
        {
            if (!shown && sw.ElapsedMilliseconds > 400)
            {
                form.Show();
                form.Refresh();
                shown = true;
            }
            if (shown)
            {
                Application.DoEvents();
            }
            Thread.Sleep(40);
        }
        if (shown)
        {
            form.Hide();
        }
        form.Dispose();

        return error;
    }

    // Se puede reemplazar la instalacion? Solo si su .exe no esta mapeado por un proceso
    // vivo: Windows deja renombrar una carpeta con ficheros en uso, asi que preguntarlo
    // por el exe (apertura en exclusiva) es la unica comprobacion fiable.
    static bool IsReplaceable(string hostDir)
    {
        string exe = Path.Combine(hostDir, "CoreFrame.exe");
        if (!File.Exists(exe))
        {
            return true;
        }
        try
        {
            using (FileStream probe = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.None))
            {
                return true;
            }
        }
        catch (Exception)
        {
            return false;
        }
    }

    static Form MakeForm(string hostDir)
    {
        Form f = new Form();
        f.FormBorderStyle = FormBorderStyle.None;
        f.StartPosition = FormStartPosition.CenterScreen;
        f.Size = new Size(460, 120);
        f.TopMost = true;
        f.ShowInTaskbar = true;
        f.BackColor = Color.FromArgb(28, 28, 32);
        f.Text = "CoreFrame";
        try
        {
            // El icono de la ventana de progreso (y de su entrada en la barra de tareas) es el
            // que va embebido en el propio .exe; si no tuviera, sale el generico y no se rompe.
            f.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        }
        catch (Exception)
        {
        }

        Label title = new Label();
        title.Text = "Preparando CoreFrame";
        title.ForeColor = Color.White;
        title.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
        title.AutoSize = true;
        title.Location = new Point(22, 20);
        f.Controls.Add(title);

        Label sub = new Label();
        sub.Text = "Primera ejecucion: se copian los archivos en\n" + hostDir + "\nPuede tardar unos segundos.";
        sub.ForeColor = Color.FromArgb(190, 190, 200);
        sub.Font = new Font("Segoe UI", 9F);
        sub.AutoSize = true;
        sub.Location = new Point(24, 50);
        f.Controls.Add(sub);

        ProgressBar bar = new ProgressBar();
        bar.Style = ProgressBarStyle.Marquee;
        bar.MarqueeAnimationSpeed = 30;
        bar.Location = new Point(24, 100);
        bar.Size = new Size(412, 6);
        f.Controls.Add(bar);

        return f;
    }

    static void CopyRange(string src, long offset, long length, string dst)
    {
        using (FileStream input = File.OpenRead(src))
        using (FileStream output = File.Create(dst))
        {
            input.Seek(offset, SeekOrigin.Begin);
            byte[] buffer = new byte[1024 * 1024];
            long left = length;
            while (left > 0)
            {
                int want = (int)Math.Min((long)buffer.Length, left);
                int got = input.Read(buffer, 0, want);
                if (got <= 0)
                {
                    throw new IOException("El paquete esta truncado.");
                }
                output.Write(buffer, 0, got);
                left -= got;
            }
        }
    }

    static int ReadFull(Stream s, byte[] buffer, int count)
    {
        int total = 0;
        while (total < count)
        {
            int got = s.Read(buffer, total, count - total);
            if (got <= 0)
            {
                break;
            }
            total += got;
        }
        return total;
    }

    static string Hex(byte[] bytes)
    {
        char[] hex = new char[bytes.Length * 2];
        for (int i = 0; i < bytes.Length; i++)
        {
            hex[i * 2] = "0123456789abcdef"[bytes[i] >> 4];
            hex[i * 2 + 1] = "0123456789abcdef"[bytes[i] & 0x0F];
        }
        return new string(hex);
    }

    static string JoinArgs(List<string> args)
    {
        string result = "";
        for (int i = 0; i < args.Count; i++)
        {
            if (i > 0)
            {
                result += " ";
            }
            result += Quote(args[i]);
        }
        return result;
    }

    static string Quote(string value)
    {
        if (value.Length > 0 && value.IndexOf(' ') < 0 && value.IndexOf('"') < 0)
        {
            return value;
        }
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    // El antivirus puede tener un handle sobre ficheros recien escritos unos cientos de
    // milisegundos, asi que un unico intento no basta. Si aun asi falla, no pasa nada:
    // el .old se queda y el proximo arranque lo borra.
    static bool TryDeleteDir(string path)
    {
        for (int attempt = 0; attempt < 4; attempt++)
        {
            try
            {
                if (Directory.Exists(path))
                {
                    Directory.Delete(path, true);
                }
                return true;
            }
            catch (Exception)
            {
                Thread.Sleep(250);
            }
        }
        return false;
    }

    static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (Exception)
        {
        }
    }

    static int Fail(string message)
    {
        try
        {
            MessageBox.Show(message, "CoreFrame", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        catch (Exception)
        {
        }
        return 1;
    }
}
