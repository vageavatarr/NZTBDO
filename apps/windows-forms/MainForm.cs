using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace NZTBDO.WinForms;

public sealed class MainForm : Form
{
    private static readonly Regex SessionIdPattern = new(
        @"^\d{8}T\d{6}Z-[0-9a-f]{8}$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase
    );

    private readonly Label _statusValue = new() { AutoSize = true, Text = "Idle" };
    private readonly Label _elapsedValue = new() { AutoSize = true, Text = "00:00:00" };
    private readonly Label _sessionValue = new() { AutoSize = true, Text = "-" };
    private readonly Label _eventsValue = new() { AutoSize = true, Text = "0" };
    private readonly Label _pausedValue = new() { AutoSize = true, Text = "0" };
    private readonly Label _guardValue = new() { AutoSize = true, Text = "0" };
    private readonly Label _writingValue = new() { AutoSize = true, Text = "-" };
    private readonly Label _lastEventAgeValue = new() { AutoSize = true, Text = "-" };
    private readonly Label _pidValue = new() { AutoSize = true, Text = "-" };
    private readonly TextBox _outputBox = new()
    {
        Multiline = true,
        ScrollBars = ScrollBars.Vertical,
        ReadOnly = true,
        Height = 130,
        Dock = DockStyle.Bottom
    };

    private readonly Button _startButton = new() { Text = "Start", Width = 120 };
    private readonly Button _testSkillsButton = new() { Text = "Test Skills", Width = 120 };
    private readonly Button _stopButton = new() { Text = "Stop", Width = 120, Enabled = false };

    private readonly System.Windows.Forms.Timer _uiTimer = new() { Interval = 1000 };
    private Process? _process;
    private DateTime _startedAtUtc;
    private string? _repoRoot;
    private string? _activeSessionDir;
    private HashSet<string> _knownSessionIds = new(StringComparer.OrdinalIgnoreCase);
    private string? _lastEventsReadError;
    private DateTime _lastEventsWriteUtc = DateTime.MinValue;

    public MainForm()
    {
        Text = "NZTBDO Session Monitor";
        Width = 760;
        Height = 480;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;

        _repoRoot = FindRepoRoot();
        BuildLayout();
        BindEvents();
        _uiTimer.Start();
        RefreshUi();
    }

    private void BuildLayout()
    {
        var panel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 11,
            Padding = new Padding(14),
            AutoSize = true
        };
        panel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 210));
        panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        AddRow(panel, 0, "Status", _statusValue);
        AddRow(panel, 1, "Elapsed", _elapsedValue);
        AddRow(panel, 2, "Session", _sessionValue);
        AddRow(panel, 3, "Events", _eventsValue);
        AddRow(panel, 4, "Paused Ticks", _pausedValue);
        AddRow(panel, 5, "Guard Blocked", _guardValue);
        AddRow(panel, 6, "Writing", _writingValue);
        AddRow(panel, 7, "Last Event Age", _lastEventAgeValue);
        AddRow(panel, 8, "Process PID", _pidValue);

        var buttonsPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight
        };
        buttonsPanel.Controls.Add(_startButton);
        buttonsPanel.Controls.Add(_testSkillsButton);
        buttonsPanel.Controls.Add(_stopButton);
        panel.Controls.Add(new Label { Text = "Control", AutoSize = true }, 0, 9);
        panel.Controls.Add(buttonsPanel, 1, 9);

        panel.Controls.Add(new Label { Text = "Output", AutoSize = true }, 0, 10);
        panel.Controls.Add(new Label { Text = "JSON summary at end of run", AutoSize = true }, 1, 10);

        Controls.Add(panel);
        Controls.Add(_outputBox);
    }

    private static void AddRow(TableLayoutPanel panel, int row, string label, Control value)
    {
        panel.Controls.Add(new Label { Text = label, AutoSize = true }, 0, row);
        panel.Controls.Add(value, 1, row);
    }

    private void BindEvents()
    {
        _startButton.Click += (_, _) => StartSession();
        _testSkillsButton.Click += (_, _) => StartSkillTest();
        _stopButton.Click += (_, _) => StopSession();
        _uiTimer.Tick += (_, _) => RefreshUi();
        FormClosing += (_, _) => StopSession();
    }

    private void StartSession()
    {
        StartProcess(
            arguments: "-m nztbdo_orchestrator.run_session --profile live_farm --ticks 12000 --tick-sleep 0.05 --start-delay 2 --quiet-runtime",
            statusText: "Running Session"
        );
    }

    private void StartSkillTest()
    {
        StartProcess(
            arguments: "-m nztbdo_orchestrator.skill_test --profile live_farm --repeats 1 --step-delay 0.5",
            statusText: "Running Skill Test"
        );
    }

    private void StartProcess(string arguments, string statusText)
    {
        if (_process is not null || _repoRoot is null)
        {
            return;
        }

        KillOrphanedBotProcesses();

        var workingDir = Path.Combine(_repoRoot, "services", "orchestrator");
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            Arguments = arguments,
            WorkingDirectory = workingDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        psi.Environment["PYTHONPATH"] = "src";

        _process = new Process
        {
            StartInfo = psi,
            EnableRaisingEvents = true
        };
        _process.Exited += (_, _) => BeginInvoke(new Action(OnProcessExited));
        _process.OutputDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data))
            {
                BeginInvoke(new Action(() => AppendOutput(e.Data!)));
            }
        };
        _process.ErrorDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data))
            {
                BeginInvoke(new Action(() => AppendOutput("[ERR] " + e.Data)));
            }
        };

        try
        {
            _process.Start();
        }
        catch (Exception ex)
        {
            AppendOutput("[ERR] Failed to start process: " + ex.Message);
            _process.Dispose();
            _process = null;
            return;
        }
        _process.BeginOutputReadLine();
        _process.BeginErrorReadLine();
        _startedAtUtc = DateTime.UtcNow;
        _activeSessionDir = null;
        _knownSessionIds = LoadSessionIds(Path.Combine(_repoRoot, "data", "logs"));
        _lastEventsReadError = null;
        _lastEventsWriteUtc = DateTime.MinValue;

        _statusValue.Text = statusText;
        _pidValue.Text = _process.Id.ToString();
        _startButton.Enabled = false;
        _testSkillsButton.Enabled = false;
        _stopButton.Enabled = true;
        _uiTimer.Start();
        RefreshUi();
    }

    private void StopSession()
    {
        try
        {
            if (_process is not null && !_process.HasExited)
            {
                _process.Kill(entireProcessTree: true);
            }
        }
        catch
        {
            // Ignore stop errors to keep UI responsive.
        }
        finally
        {
            KillOrphanedBotProcesses();
        }
    }

    private void OnProcessExited()
    {
        _statusValue.Text = "Stopped";
        _startButton.Enabled = true;
        _testSkillsButton.Enabled = true;
        _stopButton.Enabled = false;
        _pidValue.Text = "-";

        _process?.Dispose();
        _process = null;
        _activeSessionDir = null;
        _knownSessionIds.Clear();
        _lastEventsWriteUtc = DateTime.MinValue;
        _uiTimer.Start();
        RefreshUi();
    }

    private void RefreshUi()
    {
        if (_process is not null)
        {
            var elapsed = DateTime.UtcNow - _startedAtUtc;
            _elapsedValue.Text = elapsed.ToString(@"hh\:mm\:ss");
        }
        else
        {
            _elapsedValue.Text = "00:00:00";
        }

        if (_repoRoot is null)
        {
            _statusValue.Text = "Repo not found";
            return;
        }

        var logsRoot = Path.Combine(_repoRoot, "data", "logs");
        var sessionDir = ResolveSessionDir(logsRoot);
        _sessionValue.Text = sessionDir is null ? "-" : Path.GetFileName(sessionDir);
        if (sessionDir is null)
        {
            _writingValue.Text = "No";
            _lastEventAgeValue.Text = "-";
            return;
        }

        var eventsFile = Path.Combine(sessionDir, "events.jsonl");
        if (!File.Exists(eventsFile))
        {
            _eventsValue.Text = "0";
            _pausedValue.Text = "0";
            _guardValue.Text = "0";
            _writingValue.Text = "No";
            _lastEventAgeValue.Text = "-";
            return;
        }

        try
        {
            var stats = CountEventStats(eventsFile);
            _eventsValue.Text = stats.total.ToString();
            _pausedValue.Text = stats.paused.ToString();
            _guardValue.Text = stats.guardBlocked.ToString();
            _lastEventsWriteUtc = File.GetLastWriteTimeUtc(eventsFile);
            var idleSeconds = Math.Max(0, (DateTime.UtcNow - _lastEventsWriteUtc).TotalSeconds);
            _lastEventAgeValue.Text = $"{idleSeconds:0.0}s";
            _writingValue.Text = idleSeconds <= 2.5 ? "Yes" : "No";
            _lastEventsReadError = null;
        }
        catch (Exception ex)
        {
            _eventsValue.Text = "0";
            _pausedValue.Text = "0";
            _guardValue.Text = "0";
            _writingValue.Text = "No";
            _lastEventAgeValue.Text = "-";
            if (!string.Equals(_lastEventsReadError, ex.Message, StringComparison.Ordinal))
            {
                _lastEventsReadError = ex.Message;
                AppendOutput("[ERR] Failed to read events: " + ex.Message);
            }
        }
    }

    private static (int total, int paused, int guardBlocked) CountEventStats(string eventsFile)
    {
        var total = 0;
        var paused = 0;
        var guardBlocked = 0;
        using var stream = new FileStream(
            eventsFile,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete
        );
        using var reader = new StreamReader(stream);
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }
            total++;
            if (line.Contains("\"fsm_state\":\"PAUSED\"", StringComparison.Ordinal))
            {
                paused++;
            }
            if (line.Contains("\"reason\":\"window_guard_blocked\"", StringComparison.Ordinal))
            {
                guardBlocked++;
            }
        }
        return (total, paused, guardBlocked);
    }

    private string? ResolveSessionDir(string logsRoot)
    {
        if (_process is not null)
        {
            if (!string.IsNullOrWhiteSpace(_activeSessionDir) && Directory.Exists(_activeSessionDir))
            {
                return _activeSessionDir;
            }

            var newSession = GetNewestUnknownSessionDir(logsRoot, _knownSessionIds);
            if (!string.IsNullOrWhiteSpace(newSession))
            {
                _activeSessionDir = newSession;
                return _activeSessionDir;
            }

            var candidate = GetLatestSessionSince(logsRoot, _startedAtUtc.AddSeconds(-30));
            if (!string.IsNullOrWhiteSpace(candidate))
            {
                _activeSessionDir = candidate;
                return _activeSessionDir;
            }
        }

        return GetLatestSessionDir(logsRoot)?.FullName;
    }

    private static DirectoryInfo? GetLatestSessionDir(string logsRoot)
    {
        DirectoryInfo? best = null;
        DateTime bestWrite = DateTime.MinValue;
        foreach (var sessionDir in EnumerateSessionDirs(logsRoot))
        {
            var eventsFile = Path.Combine(sessionDir.FullName, "events.jsonl");
            var writeTime = File.Exists(eventsFile)
                ? File.GetLastWriteTimeUtc(eventsFile)
                : sessionDir.LastWriteTimeUtc;
            if (writeTime > bestWrite)
            {
                bestWrite = writeTime;
                best = sessionDir;
            }
        }

        return best;
    }

    private static HashSet<string> LoadSessionIds(string logsRoot)
    {
        var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var sessionDir in EnumerateSessionDirs(logsRoot))
        {
            result.Add(sessionDir.Name);
        }

        return result;
    }

    private static string? GetNewestUnknownSessionDir(string logsRoot, HashSet<string> knownSessionIds)
    {
        DirectoryInfo? best = null;
        DateTime bestWrite = DateTime.MinValue;
        foreach (var sessionDir in EnumerateSessionDirs(logsRoot))
        {
            if (knownSessionIds.Contains(sessionDir.Name))
            {
                continue;
            }

            var eventsFile = Path.Combine(sessionDir.FullName, "events.jsonl");
            var writeTime = File.Exists(eventsFile)
                ? File.GetLastWriteTimeUtc(eventsFile)
                : sessionDir.LastWriteTimeUtc;
            if (writeTime <= bestWrite)
            {
                continue;
            }

            bestWrite = writeTime;
            best = sessionDir;
        }

        return best?.FullName;
    }

    private static string? GetLatestSessionSince(string logsRoot, DateTime minUtc)
    {
        string? best = null;
        DateTime bestWrite = DateTime.MinValue;
        foreach (var sessionDir in EnumerateSessionDirs(logsRoot))
        {
            var eventsFile = Path.Combine(sessionDir.FullName, "events.jsonl");
            var writeTime = File.Exists(eventsFile)
                ? File.GetLastWriteTimeUtc(eventsFile)
                : sessionDir.LastWriteTimeUtc;
            if (writeTime < minUtc || writeTime <= bestWrite)
            {
                continue;
            }

            bestWrite = writeTime;
            best = sessionDir.FullName;
        }

        return best;
    }

    private static IEnumerable<DirectoryInfo> EnumerateSessionDirs(string logsRoot)
    {
        var dir = new DirectoryInfo(logsRoot);
        if (!dir.Exists)
        {
            yield break;
        }

        foreach (var sessionDir in dir.GetDirectories())
        {
            if (!SessionIdPattern.IsMatch(sessionDir.Name))
            {
                continue;
            }
            yield return sessionDir;
        }
    }

    private static string? FindRepoRoot()
    {
        var path = AppContext.BaseDirectory;
        var dir = new DirectoryInfo(path);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "ROADMAP.md")))
            {
                return dir.FullName;
            }
            dir = dir.Parent;
        }
        return null;
    }

    private void AppendOutput(string line)
    {
        if (line.StartsWith("{", StringComparison.Ordinal))
        {
            // Pretty-print final JSON output to make scan easier.
            try
            {
                var doc = JsonDocument.Parse(line);
                var pretty = JsonSerializer.Serialize(doc, new JsonSerializerOptions { WriteIndented = true });
                line = pretty;
            }
            catch
            {
                // Keep raw line if parsing fails.
            }
        }

        _outputBox.AppendText(line + Environment.NewLine);
    }

    private void KillOrphanedBotProcesses()
    {
        try
        {
            var script =
                "Get-CimInstance Win32_Process | " +
                "Where-Object { ($_.Name -match 'python|cmd') -and $_.CommandLine -match 'nztbdo_orchestrator\\.(run_session|runtime_loop|skill_test|run_profile)' } | " +
                "ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }";
            using var killer = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "powershell",
                    Arguments = "-NoProfile -WindowStyle Hidden -Command \"" + script + "\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                }
            };
            killer.Start();
            killer.WaitForExit(5000);
        }
        catch
        {
            // Non-fatal: best-effort cleanup.
        }
    }
}
