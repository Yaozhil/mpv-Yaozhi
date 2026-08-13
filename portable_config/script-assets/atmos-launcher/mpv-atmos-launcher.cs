// SPDX-License-Identifier: MIT
// Dedicated bootstrapper for the optional mpv-Yaozhi Atmos experiment.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class AtmosManifest
{
    internal const string PlayerVersion = "mpv-v0.4.2-fel-beta.1";
    internal const string BridgeVersion = "v0.7.3";
    internal const string InstallVersion = "mpv-v0.4.2-fel-beta.1__bridge-v0.7.3";

    internal const string PlayerFile = "mpv-omniphony-fel-windows-x86_64.zip";
    internal const string BridgeFile = "harletty-bridge-v0.7.3-windows-x86_64.zip";

    internal const string PlayerUrl =
        "https://github.com/mgth/Omniphony/releases/download/"
        + PlayerVersion + "/" + PlayerFile;
    internal const string BridgeUrl =
        "https://github.com/harletty/harletty-bridge/releases/download/"
        + BridgeVersion + "/" + BridgeFile;

    internal const string PlayerSha256 =
        "52eba88d97dffcec88afb3b51c261e3cf2183f992028f2b8d18fa20783546e03";
    internal const string BridgeSha256 =
        "a2cee380f7607f9b1fedd3cd3316dcb5d2721a2f4610ad224816905dec676d5d";

    internal const string Marker =
        "mpv-Yaozhi Atmos experiment\r\n"
        + "player=mpv-v0.4.2-fel-beta.1\r\n"
        + "engine=liborender-v0.4.2\r\n"
        + "bridge=v0.7.3\r\n";
}

internal sealed class AtmosPaths
{
    internal readonly string Root;
    internal readonly string Config;
    internal readonly string Cache;
    internal readonly string InstallRoot;
    internal readonly string Install;

    internal AtmosPaths()
    {
        Root = Path.GetFullPath(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));
        Config = Path.Combine(Root, "portable_config");
        Cache = Path.Combine(Config, "cache", "atmos-components");
        InstallRoot = Path.Combine(Config, "experimental", "omniphony");
        Install = Path.Combine(InstallRoot, AtmosManifest.InstallVersion);
    }
}

internal static class AtmosBootstrap
{
    internal delegate void ProgressReporter(string message, int percent);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate uint VersionFunction();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryW(string fileName);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr module, string name);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool FreeLibrary(IntPtr module);

    internal static bool IsReady(AtmosPaths paths)
    {
        string marker = Path.Combine(paths.Install, "mpv-yaozhi-atmos.version");
        return File.Exists(Path.Combine(paths.Install, "mpv.exe"))
            && File.Exists(Path.Combine(paths.Install, "orender.dll"))
            && File.Exists(Path.Combine(paths.Install, "harletty_bridge.dll"))
            && File.Exists(marker)
            && File.ReadAllText(marker, Encoding.UTF8).Replace("\n", "\r\n")
                .Replace("\r\r\n", "\r\n") == AtmosManifest.Marker;
    }

    internal static void ValidateRuntime(AtmosPaths paths)
    {
        ValidatePlayerCapabilities(paths);

        string engine = Path.Combine(paths.Install, "orender.dll");
        IntPtr module = LoadLibraryW(engine);
        if (module == IntPtr.Zero)
            throw new Win32Exception(
                Marshal.GetLastWin32Error(),
                "无法加载侧车 orender.dll");

        try {
            IntPtr majorAddress = GetProcAddress(module, "orender_version_major");
            IntPtr minorAddress = GetProcAddress(module, "orender_version_minor");
            if (majorAddress == IntPtr.Zero || minorAddress == IntPtr.Zero)
                throw new InvalidDataException("侧车 orender.dll 缺少 ABI 版本接口。");

            VersionFunction major = (VersionFunction)Marshal.GetDelegateForFunctionPointer(
                majorAddress, typeof(VersionFunction));
            VersionFunction minor = (VersionFunction)Marshal.GetDelegateForFunctionPointer(
                minorAddress, typeof(VersionFunction));
            uint actualMajor = major();
            uint actualMinor = minor();
            if (actualMajor != 0 || actualMinor < 5)
                throw new InvalidDataException(
                    "侧车 liborender ABI 不兼容：实际 "
                    + actualMajor + "." + actualMinor + "，需要 0.5 或更高兼容版本。");
        } finally {
            FreeLibrary(module);
        }
    }

    private static void ValidatePlayerCapabilities(AtmosPaths paths)
    {
        string console = Path.Combine(paths.Install, "mpv.com");
        if (!File.Exists(console))
            throw new FileNotFoundException("侧车缺少 mpv.com，无法校验核心能力。", console);

        Process probe = Process.Start(new ProcessStartInfo {
            FileName = console,
            Arguments = "--no-config --list-options",
            WorkingDirectory = paths.Install,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        });
        string output = probe.StandardOutput.ReadToEnd();
        string error = probe.StandardError.ReadToEnd();
        probe.WaitForExit();
        if (probe.ExitCode != 0)
            throw new InvalidDataException(
                "侧车核心能力检查失败：" + error.Trim());
        if (output.IndexOf("--ad-orender-library", StringComparison.Ordinal) < 0
            || output.IndexOf("--image-subs-colorspace", StringComparison.Ordinal) < 0)
            throw new InvalidDataException(
                "侧车核心不是 mpv-Yaozhi Atmos HDR/PGS 定制构建。\r\n"
                + "已拒绝缺少 Atmos 引擎固定或 HDR 图形字幕能力的通用版本。");
    }

    internal static string Prepare(AtmosPaths paths, ProgressReporter report)
    {
        if (IsReady(paths))
            return paths.Install;

        Directory.CreateDirectory(paths.Cache);
        Directory.CreateDirectory(paths.InstallRoot);

        string playerArchive = Path.Combine(paths.Cache, AtmosManifest.PlayerFile);
        string bridgeArchive = Path.Combine(paths.Cache, AtmosManifest.BridgeFile);

        EnsureArchive(
            AtmosManifest.PlayerUrl,
            playerArchive,
            AtmosManifest.PlayerSha256,
            "正在获取 Atmos 实验播放器",
            0,
            92,
            report);
        EnsureArchive(
            AtmosManifest.BridgeUrl,
            bridgeArchive,
            AtmosManifest.BridgeSha256,
            "正在获取解码桥",
            92,
            7,
            report);

        report("正在校验并部署到独立目录", 99);
        InstallArchives(paths, playerArchive, bridgeArchive);

        if (!IsReady(paths))
            throw new InvalidDataException("组件部署后完整性检查失败。");

        report("Atmos 实验组件已准备完成", 100);
        return paths.Install;
    }

    private static void EnsureArchive(
        string url,
        string destination,
        string expectedSha256,
        string label,
        int basePercent,
        int percentSpan,
        ProgressReporter report)
    {
        if (File.Exists(destination)) {
            report(label + "：校验本地缓存", basePercent);
            if (HashFile(destination) == expectedSha256)
                return;
            MoveAside(destination, "invalid");
        }

        string partial = destination + ".partial";
        if (File.Exists(partial))
            File.Delete(partial);

        Exception lastError = null;
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                Download(
                    url,
                    partial,
                    delegate(long received, long total) {
                        int local = total > 0
                            ? (int)Math.Min(100, received * 100L / total)
                            : 0;
                        int overall = basePercent + local * percentSpan / 100;
                        report(label + "（第 " + attempt + "/3 次）", overall);
                    });

                string actual = HashFile(partial);
                if (actual != expectedSha256)
                    throw new InvalidDataException(
                        "SHA-256 不匹配：期望 " + expectedSha256 + "，实际 " + actual);

                if (File.Exists(destination))
                    MoveAside(destination, "old");
                File.Move(partial, destination);
                return;
            } catch (Exception ex) {
                lastError = ex;
                if (File.Exists(partial))
                    File.Delete(partial);
                if (attempt < 3)
                    Thread.Sleep(attempt * 1200);
            }
        }

        throw new IOException(label + "失败。", lastError);
    }

    private static void Download(
        string url,
        string destination,
        Action<long, long> progress)
    {
        HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
        request.AllowAutoRedirect = true;
        request.AutomaticDecompression =
            DecompressionMethods.GZip | DecompressionMethods.Deflate;
        request.Timeout = 30000;
        request.ReadWriteTimeout = 30000;
        request.UserAgent = "mpv-Yaozhi-Atmos-Launcher/1.0";

        using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
        using (Stream input = response.GetResponseStream())
        using (FileStream output = new FileStream(
            destination, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            long total = response.ContentLength;
            long received = 0;
            byte[] buffer = new byte[128 * 1024];
            int read;
            while ((read = input.Read(buffer, 0, buffer.Length)) > 0) {
                output.Write(buffer, 0, read);
                received += read;
                progress(received, total);
            }
            output.Flush(true);
        }
    }

    private static string HashFile(string path)
    {
        using (SHA256 sha = SHA256.Create())
        using (FileStream input = File.OpenRead(path))
        {
            byte[] hash = sha.ComputeHash(input);
            StringBuilder text = new StringBuilder(hash.Length * 2);
            foreach (byte value in hash)
                text.Append(value.ToString("x2"));
            return text.ToString();
        }
    }

    private static void InstallArchives(
        AtmosPaths paths,
        string playerArchive,
        string bridgeArchive)
    {
        string staging = Path.Combine(
            paths.InstallRoot, ".staging-" + Guid.NewGuid().ToString("N"));
        string playerStage = Path.Combine(staging, "player");
        string bridgeStage = Path.Combine(staging, "bridge");
        Directory.CreateDirectory(playerStage);
        Directory.CreateDirectory(bridgeStage);

        try {
            ZipFile.ExtractToDirectory(playerArchive, playerStage);
            ZipFile.ExtractToDirectory(bridgeArchive, bridgeStage);

            string playerExe = FindFile(playerStage, "mpv.exe");
            string engine = FindFile(playerStage, "orender.dll");
            string bridge = FindFile(bridgeStage, "harletty_bridge.dll");
            if (playerExe == null || engine == null || bridge == null)
                throw new InvalidDataException("上游压缩包缺少 mpv.exe、orender.dll 或解码桥。");

            string playerRoot = Path.GetDirectoryName(playerExe);
            if (!SameDirectory(Path.GetDirectoryName(engine), playerRoot))
                File.Copy(engine, Path.Combine(playerRoot, "orender.dll"), true);
            File.Copy(bridge, Path.Combine(playerRoot, "harletty_bridge.dll"), true);
            File.WriteAllText(
                Path.Combine(playerRoot, "mpv-yaozhi-atmos.version"),
                AtmosManifest.Marker,
                new UTF8Encoding(false));

            if (Directory.Exists(paths.Install))
                MoveAside(paths.Install, "invalid");
            Directory.Move(playerRoot, paths.Install);
        } finally {
            if (Directory.Exists(staging))
                Directory.Delete(staging, true);
        }
    }

    private static string FindFile(string root, string name)
    {
        string[] files = Directory.GetFiles(root, name, SearchOption.AllDirectories);
        return files.Length > 0 ? files[0] : null;
    }

    private static bool SameDirectory(string left, string right)
    {
        return string.Equals(
            Path.GetFullPath(left).TrimEnd(Path.DirectorySeparatorChar),
            Path.GetFullPath(right).TrimEnd(Path.DirectorySeparatorChar),
            StringComparison.OrdinalIgnoreCase);
    }

    private static void MoveAside(string path, string label)
    {
        string moved = path + "." + label + "-"
            + DateTime.UtcNow.ToString("yyyyMMddHHmmssfff");
        if (File.Exists(path))
            File.Move(path, moved);
        else if (Directory.Exists(path))
            Directory.Move(path, moved);
    }
}

internal sealed class PrepareForm : Form
{
    private readonly AtmosPaths paths;
    private readonly Label status;
    private readonly ProgressBar progress;

    internal string ResultPath;
    internal Exception Failure;

    internal PrepareForm(AtmosPaths paths)
    {
        this.paths = paths;
        Text = "mpv-Yaozhi · Atmos 实验组件";
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        ClientSize = new Size(460, 112);

        status = new Label();
        status.AutoSize = false;
        status.Location = new Point(20, 18);
        status.Size = new Size(420, 42);
        status.Text = "正在准备实验组件…";
        Controls.Add(status);

        progress = new ProgressBar();
        progress.Location = new Point(20, 70);
        progress.Size = new Size(420, 20);
        progress.Minimum = 0;
        progress.Maximum = 100;
        Controls.Add(progress);
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        ThreadPool.QueueUserWorkItem(delegate {
            try {
                ResultPath = AtmosBootstrap.Prepare(paths, Report);
            } catch (Exception ex) {
                Failure = ex;
            }
            BeginInvoke((MethodInvoker)delegate { Close(); });
        });
    }

    private void Report(string message, int value)
    {
        if (IsDisposed)
            return;
        BeginInvoke((MethodInvoker)delegate {
            status.Text = message;
            progress.Value = Math.Max(0, Math.Min(100, value));
        });
    }
}

internal static class AtmosLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        AtmosPaths paths = new AtmosPaths();
        if (!File.Exists(Path.Combine(paths.Root, "mpv.exe"))
            || !Directory.Exists(paths.Config))
        {
            MessageBox.Show(
                "请把 mpv-Atmos.exe 放在 mpv.exe 与 portable_config 所在的启动目录。",
                "mpv-Yaozhi · Atmos 实验模式",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 2;
        }

        if (!AtmosBootstrap.IsReady(paths)) {
            DialogResult consent = MessageBox.Show(
                "Atmos 实验模式将从官方 GitHub 获取并校验约 37 MB 的独立组件。\r\n\r\n"
                + "实验播放器：mgth/Omniphony（GPL-3.0-or-later）\r\n"
                + "解码桥：harletty/harletty-bridge（由用户本机直接获取，"
                + "不随 mpv-Yaozhi 发布包再分发）\r\n\r\n"
                + "普通 mpv.exe 不会被替换。若准备或启动失败，将自动改用原生播放器。",
                "首次启用 Atmos 实验模式",
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Information);
            if (consent != DialogResult.OK) {
                LaunchNative(paths, args);
                return 0;
            }

            using (PrepareForm form = new PrepareForm(paths)) {
                form.ShowDialog();
                if (form.Failure != null) {
                    MessageBox.Show(
                        "Atmos 实验组件准备失败，已改用原生播放器。\r\n\r\n"
                        + FlattenError(form.Failure)
                        + "\r\n\r\n也可把官方压缩包放入：\r\n" + paths.Cache,
                        "mpv-Yaozhi · 已安全回退",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning);
                    LaunchNative(paths, args);
                    return 1;
                }
            }
        }

        try {
            AtmosBootstrap.ValidateRuntime(paths);
            Process process = LaunchAtmos(paths, args);
            if (process.WaitForExit(8000) && process.ExitCode != 0) {
                MessageBox.Show(
                    "Atmos 实验播放器未能正常启动，已改用原生播放器。",
                    "mpv-Yaozhi · 已安全回退",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                LaunchNative(paths, args);
                return process.ExitCode;
            }
            return 0;
        } catch (Exception ex) {
            MessageBox.Show(
                "Atmos 实验播放器启动失败，已改用原生播放器。\r\n\r\n"
                + FlattenError(ex),
                "mpv-Yaozhi · 已安全回退",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            LaunchNative(paths, args);
            return 1;
        }
    }

    private static Process LaunchAtmos(AtmosPaths paths, string[] args)
    {
        string player = Path.Combine(paths.Install, "mpv.exe");
        string engine = Path.Combine(paths.Install, "orender.dll");
        string bridge = Path.Combine(paths.Install, "harletty_bridge.dll");

        List<string> all = new List<string>();
        all.Add("--config-dir=" + paths.Config);
        all.Add("--ad=orender");
        all.Add("--ad-orender-library=" + engine);
        all.Add("--ad-orender-bridge-path=" + bridge);
        all.Add("--ad-orender-host-decoder=lavc");
        all.Add("--script-opts-append=yaozhi_atmos_mode-enabled=yes");
        AddUserArguments(all, args);

        return Process.Start(new ProcessStartInfo {
            FileName = player,
            Arguments = JoinArguments(all),
            WorkingDirectory = paths.Root,
            UseShellExecute = false,
        });
    }

    private static void AddUserArguments(List<string> all, string[] args)
    {
        bool skipValue = false;
        foreach (string arg in args) {
            if (skipValue) {
                skipValue = false;
                continue;
            }

            if (arg == "--ad-orender-library" || arg == "--ad-orender-bridge-path") {
                skipValue = true;
                continue;
            }
            if (arg.StartsWith("--ad-orender-library=", StringComparison.Ordinal)
                || arg.StartsWith("--ad-orender-bridge-path=", StringComparison.Ordinal))
                continue;

            all.Add(arg);
        }
    }

    private static void LaunchNative(AtmosPaths paths, string[] args)
    {
        Process.Start(new ProcessStartInfo {
            FileName = Path.Combine(paths.Root, "mpv.exe"),
            Arguments = JoinArguments(new List<string>(args)),
            WorkingDirectory = paths.Root,
            UseShellExecute = false,
        });
    }

    private static string JoinArguments(IEnumerable<string> args)
    {
        StringBuilder line = new StringBuilder();
        foreach (string arg in args) {
            if (line.Length > 0)
                line.Append(' ');
            line.Append(QuoteArgument(arg));
        }
        return line.ToString();
    }

    private static string QuoteArgument(string value)
    {
        if (value.Length > 0
            && value.IndexOfAny(new char[] {' ', '\t', '\n', '\v', '"'}) < 0)
            return value;

        StringBuilder quoted = new StringBuilder();
        quoted.Append('"');
        int backslashes = 0;
        foreach (char character in value) {
            if (character == '\\') {
                backslashes++;
            } else if (character == '"') {
                quoted.Append('\\', backslashes * 2 + 1);
                quoted.Append('"');
                backslashes = 0;
            } else {
                quoted.Append('\\', backslashes);
                quoted.Append(character);
                backslashes = 0;
            }
        }
        quoted.Append('\\', backslashes * 2);
        quoted.Append('"');
        return quoted.ToString();
    }

    private static string FlattenError(Exception error)
    {
        StringBuilder text = new StringBuilder();
        Exception current = error;
        while (current != null) {
            if (text.Length > 0)
                text.Append("\r\n");
            text.Append(current.Message);
            current = current.InnerException;
        }
        return text.ToString();
    }
}
