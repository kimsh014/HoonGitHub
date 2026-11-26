// 번호 창. 판매 프로그램 옆에 항상 위로 떠 있는 좁은 창이다.
// - 눌러도 판매 프로그램의 포커스를 빼앗지 않는다(WS_EX_NOACTIVATE). 화상 키보드처럼 동작한다.
// - 닫기(X)는 최소화로 바뀐다. 최소화되어 있어도 숫자패드는 받고, 키가 들어오면 창을 다시 보인다(M-16).
// - 서버와 이야기는 작업 스레드 하나가 순서대로 한다(보내기가 먼저, 없으면 10초마다 TV 번호 목록 확인,
//   끊겼거나 못 보낸 번호가 있으면 3초마다). 서버 요청 기록이 쌓이지 않게 평소에는 느리게 묻는다.
// - 못 보낸 번호는 '못 보낸 번호' 목록에 두고, 서버가 돌아오면 저절로 보낸다(2분 넘은 것은 버리고 알림).
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Drawing;
using System.Media;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace MenuBoardKeypad
{
    public sealed class MainForm : Form
    {
        const int PollMs = 10000, FastPollMs = 3000;
        static readonly TimeSpan RehookEvery = TimeSpan.FromMinutes(1);
        static readonly TimeSpan RetryFor = TimeSpan.FromMinutes(2);

        sealed class Pending { public Outcome Job; public DateTime At; public bool Queued; }
        readonly List<Pending> pending = new List<Pending>(); // 화면 스레드에서만 만진다
        volatile bool fastPoll;

        public int ExitCode = 1; // 0이면 지킴이도 멈춘다
        bool exitRequested;
        bool settingsOpen;

        Settings settings;
        volatile BoardClient client;
        readonly KeypadLogic logic = new KeypadLogic();
        readonly NumpadHook hook;
        readonly BlockingCollection<Outcome> jobs = new BlockingCollection<Outcome>();
        Thread worker;
        volatile bool stopping;

        DateTime lastServerOk = DateTime.MinValue;
        DateTime lastKeyAt = DateTime.MinValue;
        DateTime lastHookAt = DateTime.MinValue;
        DateTime messageUntil = DateTime.MinValue;
        string storeName = "";
        string serverError = null;
        int selected = -1;
        DateTime selectedAt;

        float s = 1f; // 화면 배율
        Label lblStatus, lblNumLock, lblInput, lblMessage, lblListTitle, lblHelp;
        FlowLayoutPanel numbers;
        Panel actionPanel;
        Button btnRecallSel, btnCancelSel, btnSettings;
        System.Windows.Forms.Timer tick;

        static readonly Color Ok = Color.FromArgb(20, 130, 60), Bad = Color.FromArgb(200, 30, 30), Warn = Color.FromArgb(190, 110, 0);

        public MainForm()
        {
            settings = Settings.Load();
            logic.FarGap = settings.FarGap;
            client = new BoardClient(settings.ServerUrl, settings.Key);
            hook = new NumpadHook(OnHookKey);

            Text = "번호 호출";
            Font = new Font("Malgun Gothic", 10f);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            MinimizeBox = true;
            ShowInTaskbar = true;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.White;
            TopMost = settings.AlwaysOnTop;
            using (Graphics g = CreateGraphics()) s = g.DpiX / 96f;
            // 1366×768에 배율 125%처럼 창이 화면보다 커지면 화면에 맞게 줄인다
            int room = Screen.PrimaryScreen.WorkingArea.Height - SystemInformation.CaptionHeight - 16;
            if (640 * s > room) s = Math.Max(0.6f, room / 640f);
            BuildUi();
            PlaceWindow();

            tick = new System.Windows.Forms.Timer();
            tick.Interval = 1000;
            tick.Tick += delegate { OnTick(); };
        }

        int S(int px) { return (int)Math.Round(px * s); }

        // 포커스를 빼앗지 않는 창 + 작업 표시줄에는 보이게
        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= 0x08000000 /* WS_EX_NOACTIVATE */ | 0x00040000 /* WS_EX_APPWINDOW */;
                return cp;
            }
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        void BuildUi()
        {
            int w = 300, pad = 8, inner = w - pad * 2;
            ClientSize = new Size(S(w), S(640));
            lblStatus = Add(new Label(), pad, 6, inner, 22);
            lblStatus.Font = new Font(Font, FontStyle.Bold);
            lblNumLock = Add(new Label(), pad, 28, inner, 18);
            lblNumLock.ForeColor = Warn;
            lblNumLock.Font = new Font(Font.FontFamily, 9f);
            lblInput = Add(new Label(), pad, 48, inner, 72);
            lblInput.Font = new Font(Font.FontFamily, 34f, FontStyle.Bold);
            lblInput.TextAlign = ContentAlignment.MiddleCenter;
            lblInput.BorderStyle = BorderStyle.FixedSingle;
            lblInput.BackColor = Color.FromArgb(248, 248, 248);
            lblMessage = Add(new Label(), pad, 124, inner, 60);
            lblMessage.Font = new Font(Font.FontFamily, 10.5f);

            string[,] keys = {
                { "7", "8", "9", "⌫" },
                { "4", "5", "6", "다시" },
                { "1", "2", "3", "빼기" },
                { "0", "지움", "부르기", "" },
            };
            PadKey[,] map = {
                { PadKey.D7, PadKey.D8, PadKey.D9, PadKey.Dot },
                { PadKey.D4, PadKey.D5, PadKey.D6, PadKey.Plus },
                { PadKey.D1, PadKey.D2, PadKey.D3, PadKey.Minus },
                { PadKey.D0, PadKey.Star, PadKey.Enter, PadKey.Enter },
            };
            int bw = (inner - 3 * 4) / 4, bh = 52, top = 188;
            for (int r = 0; r < 4; r++)
            {
                for (int c = 0; c < 4; c++)
                {
                    if (keys[r, c].Length == 0) continue;
                    int span = keys[r, c] == "부르기" ? 2 : 1;
                    Button b = Add(new Button(), pad + c * (bw + 4), top + r * (bh + 4), bw * span + 4 * (span - 1), bh);
                    b.Text = keys[r, c];
                    b.Font = new Font(Font.FontFamily, keys[r, c].Length == 1 ? 18f : 12f, FontStyle.Bold);
                    b.FlatStyle = FlatStyle.Flat;
                    b.BackColor = span == 2 ? Color.FromArgb(200, 16, 46) : c == 3 ? Color.FromArgb(235, 235, 235) : Color.White;
                    if (span == 2) b.ForeColor = Color.White;
                    b.TabStop = false;
                    PadKey k = map[r, c];
                    b.Click += delegate { HandleKey(k); };
                }
            }

            lblListTitle = Add(new Label(), pad, 414, inner, 20);
            lblListTitle.Text = "TV에 떠 있는 번호 (누르면 다시·빼기)";
            lblListTitle.ForeColor = Color.DimGray;
            numbers = Add(new FlowLayoutPanel(), pad, 436, inner, 96);
            numbers.AutoScroll = true;
            actionPanel = Add(new Panel(), pad, 536, inner, 44);
            btnRecallSel = new Button();
            btnCancelSel = new Button();
            foreach (Button b in new[] { btnRecallSel, btnCancelSel })
            {
                b.FlatStyle = FlatStyle.Flat;
                b.Font = new Font(Font.FontFamily, 11f, FontStyle.Bold);
                b.TabStop = false;
                b.Size = new Size(S(inner / 2 - 2), S(44));
                actionPanel.Controls.Add(b);
            }
            btnCancelSel.Left = S(inner / 2 + 2);
            btnRecallSel.Click += delegate { ActOnSelected(CallAction.Recall); };
            btnCancelSel.Click += delegate { ActOnSelected(CallAction.Cancel); };
            actionPanel.Visible = false;

            lblHelp = Add(new Label(), pad, 586, inner - 64, 48);
            lblHelp.Text = "키패드: 번호+Enter 부르기\n+ 다시 · - 빼기 · . 지움";
            lblHelp.ForeColor = Color.DimGray;
            lblHelp.Font = new Font(Font.FontFamily, 9f);
            btnSettings = Add(new Button(), pad + inner - 60, 592, 60, 34);
            btnSettings.Text = "설정";
            btnSettings.TabStop = false;
            btnSettings.Click += delegate { OpenSettings(); };
        }

        T Add<T>(T c, int x, int y, int w, int h) where T : Control
        {
            c.Bounds = new Rectangle(S(x), S(y), S(w), S(h));
            Controls.Add(c);
            return c;
        }

        void PlaceWindow()
        {
            Rectangle wanted = new Rectangle(settings.Left, settings.Top, Width, Height);
            bool visible = false;
            foreach (Screen sc in Screen.AllScreens)
            {
                if (settings.Left != int.MinValue && sc.WorkingArea.Contains(new Point(wanted.Left + 40, wanted.Top + 10))) visible = true;
            }
            if (!visible)
            {
                Rectangle wa = Screen.PrimaryScreen.WorkingArea;
                wanted.Location = new Point(wa.Right - Width, Math.Max(wa.Top, wa.Bottom - Height));
            }
            Location = wanted.Location;
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            ApplyCapture();
            worker = new Thread(WorkerLoop);
            worker.IsBackground = true;
            worker.Name = "server";
            worker.Start();
            tick.Start();
            Refresh2();
            if (settings.Key.Length == 0)
            {
                BeginInvoke(new MethodInvoker(OpenSettings));
            }
        }

        void ApplyCapture()
        {
            try
            {
                if (settings.CaptureNumpad) { hook.Install(); lastHookAt = DateTime.Now; }
                else hook.Uninstall();
            }
            catch (Exception ex)
            {
                Log.Write("숫자패드 훅을 걸지 못함: " + ex.Message);
                Notify(Tone.Error, "숫자패드를 받을 수 없습니다. 화면 단추로 부르세요. (" + ex.Message + ")");
            }
        }

        // 훅 스레드(=이 화면 스레드)에서 불린다. 빨리 돌아가야 하므로 실제 처리는 BeginInvoke로 미룬다.
        bool OnHookKey(PadKey key, bool repeat)
        {
            if (!settings.CaptureNumpad || settingsOpen) return false;
            if (key == PadKey.Back && !logic.HasInput) return false; // 치던 번호가 없으면 Backspace는 판매 프로그램 것
            if (!repeat) BeginInvoke(new MethodInvoker(delegate { HandleKey(key); }));
            return true;
        }

        void HandleKey(PadKey key)
        {
            DateTime now = DateTime.Now;
            lastKeyAt = now;
            if (WindowState == FormWindowState.Minimized) ShowWindow(Handle, 4 /* SW_SHOWNOACTIVATE */);
            Outcome o = logic.Press(key, now);
            if (o.Message != null) Notify(o.Tone, o.Message);
            if (o.Send)
            {
                // 같은 번호가 못 보낸 목록에 있으면 이번 것으로 대신한다
                pending.RemoveAll(delegate (Pending p) { return p.Job.Number == o.Number && !p.Queued; });
                jobs.Add(o);
            }
            Refresh2();
        }

        void ActOnSelected(CallAction action)
        {
            if (selected < 1) return;
            int n = selected;
            SelectNumber(-1);
            logic.Reset();
            HandleKey(action == CallAction.Recall ? PadKey.Plus : PadKey.Minus);
            foreach (char ch in n.ToString()) HandleKey((PadKey)(ch - '0'));
            HandleKey(PadKey.Enter);
        }

        void SelectNumber(int n)
        {
            selected = n;
            selectedAt = DateTime.Now;
            actionPanel.Visible = n > 0;
            if (n > 0)
            {
                btnRecallSel.Text = n + "번 다시";
                btnCancelSel.Text = n + "번 빼기";
            }
        }

        void Notify(Tone tone, string message)
        {
            lblMessage.Text = message;
            lblMessage.ForeColor = tone == Tone.Error ? Bad : tone == Tone.Warn ? Warn : tone == Tone.Ok ? Ok : Color.Black;
            messageUntil = DateTime.Now.AddSeconds(tone == Tone.Error ? 30 : 10);
            if (!settings.Sound) return;
            if (tone == Tone.Error) SystemSounds.Hand.Play();
            else if (tone == Tone.Warn) SystemSounds.Exclamation.Play();
            else if (tone == Tone.Ok) SystemSounds.Asterisk.Play();
        }

        // 입력 줄·연결 상태·Num Lock 표시를 지금 상태로
        void Refresh2()
        {
            string input = logic.InputText();
            lblInput.Text = input.Length > 0 ? input : "–";
            lblInput.ForeColor = logic.Mode == CallAction.Cancel ? Bad : logic.Mode == CallAction.Recall ? Warn : Color.Black;
            bool connected = serverError == null && lastServerOk != DateTime.MinValue;
            if (settings.Key.Length == 0)
            {
                lblStatus.Text = "● 설정에서 연동 키를 넣어 주세요";
                lblStatus.ForeColor = Bad;
            }
            else if (connected)
            {
                lblStatus.Text = "● 연결됨" + (storeName.Length > 0 ? " · " + storeName : "");
                lblStatus.ForeColor = Ok;
            }
            else
            {
                lblStatus.Text = lastServerOk == DateTime.MinValue && serverError == null ? "● 서버 연결 중…" : "● 서버 연결 안 됨";
                lblStatus.ForeColor = Bad;
            }
            BackColor = connected || settings.Key.Length == 0 ? Color.White : Color.FromArgb(255, 228, 228); // 끊기면 창 전체를 붉게
            if (pending.Count > 0)
            {
                List<string> nums = new List<string>();
                foreach (Pending p in pending) nums.Add((p.Job.Action == CallAction.Cancel ? "-" : "") + p.Job.Number);
                lblNumLock.Text = "못 보낸 번호: " + string.Join(", ", nums.ToArray()) + " (서버가 돌아오면 저절로 보냄)";
                lblNumLock.ForeColor = Bad;
                return;
            }
            lblNumLock.ForeColor = Warn;
            string capture = settingsOpen ? "설정 중: 키패드가 판매 프로그램으로 갑니다 · "
                : settings.CaptureNumpad ? (hook.Installed ? "" : "숫자패드 받기 꺼짐(오류) · ") : "숫자패드 받기 꺼짐 · ";
            lblNumLock.Text = capture + (Control.IsKeyLocked(Keys.NumLock) ? "" : "Num Lock 꺼짐(그대로 써도 됩니다)");
        }

        void OnTick()
        {
            DateTime now = DateTime.Now;
            if (logic.Tick(now)) Notify(Tone.None, "입력이 멈춰 지웠습니다.");
            if (now > messageUntil && lblMessage.Text.Length > 0 && serverError == null) lblMessage.Text = "";
            if (selected > 0 && now - selectedAt > TimeSpan.FromSeconds(10)) SelectNumber(-1);
            // 판매 프로그램이 전체 화면·항상 위로 떠도 다시 위로 (포커스는 건드리지 않음)
            if (settings.AlwaysOnTop && WindowState != FormWindowState.Minimized && now.Second % 5 == 0)
            {
                SetWindowPos(Handle, (IntPtr)(-1) /* HWND_TOPMOST */, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 /* NOSIZE|NOMOVE|NOACTIVATE */);
            }
            // Windows가 응답이 늦은 훅을 말없이 뗄 수 있어 1분마다 다시 건다(새 훅을 먼저 걸어 빈틈 없음).
            if (settings.CaptureNumpad && !settingsOpen && now - lastHookAt > RehookEvery) ApplyCapture();
            DropOldPending(now);
            Refresh2();
        }

        // ── 서버 작업 스레드 ──
        void WorkerLoop()
        {
            while (!stopping)
            {
                Outcome job;
                bool got;
                try { got = jobs.TryTake(out job, fastPoll ? FastPollMs : PollMs); }
                catch (Exception) { return; }
                BoardClient c = client;
                if (got)
                {
                    try
                    {
                        CallsResult r = c.Send(job.Action, job.Number);
                        Ui(delegate { OnSent(job, r); });
                    }
                    catch (Exception ex)
                    {
                        Ui(delegate { OnSendFailed(job, ex); });
                    }
                    continue; // 응답에 TV 번호 목록이 들어 있다
                }
                try
                {
                    CallsResult r = c.GetCalls();
                    Ui(delegate { OnPolled(r, null); });
                }
                catch (Exception ex)
                {
                    Ui(delegate { OnPolled(null, ex); });
                }
            }
        }

        void Ui(MethodInvoker m)
        {
            try { if (!stopping && IsHandleCreated) BeginInvoke(m); }
            catch (Exception) { }
        }

        void OnSent(Outcome job, CallsResult r)
        {
            DateTime now = DateTime.Now;
            pending.RemoveAll(delegate (Pending p) { return p.Job == job; });
            logic.SendDone(job.Action, job.Number, r.Result, now);
            Log.Write(job.Action + " " + job.Number + " → " + r.Result);
            Notify(r.Result == "called" || r.Result == "removed" ? Tone.Ok : Tone.Info, KeypadLogic.ResultMessage(job.Action, job.Number, r.Result));
            OnPolled(r, null);
        }

        void OnSendFailed(Outcome job, Exception ex)
        {
            ServerException se = ex as ServerException;
            Log.Write(job.Action + " " + job.Number + " 실패: " + ex.Message);
            Pending mine = pending.Find(delegate (Pending p) { return p.Job == job; });
            if (se != null && se.Status >= 400 && se.Status < 500 && se.Status != 401 && se.Status != 429)
            {
                if (mine != null) pending.Remove(mine);
                Notify(Tone.Error, job.Number + "번: " + ex.Message); // 요청 자체가 틀림. 다시 보내도 같다.
            }
            else
            {
                logic.SendFailed(job.Action, job.Number, DateTime.Now);
                if (mine == null)
                {
                    mine = new Pending();
                    mine.Job = job;
                    mine.At = DateTime.Now;
                    pending.Add(mine);
                    Notify(Tone.Error, job.Number + "번을 " + (job.Action == CallAction.Cancel ? "빼지" : "부르지") + " 못했습니다. " + ex.Message + " 서버가 돌아오면 저절로 보냅니다.");
                }
                mine.Queued = false;
            }
            if (se == null || se.Status == 0 || se.Status == 401) serverError = ex.Message;
            fastPoll = pending.Count > 0 || serverError != null;
            Refresh2();
        }

        // 서버가 돌아오면 못 보낸 번호를 순서대로 다시 보낸다
        void RetryPending()
        {
            DropOldPending(DateTime.Now);
            foreach (Pending p in pending)
            {
                if (p.Queued) continue;
                p.Queued = true;
                jobs.Add(p.Job);
            }
        }

        // 2분 넘게 못 보낸 번호는 버린다(손님이 이미 받아 갔거나 직원이 다시 불렀을 것). 버린 것은 크게 알린다.
        void DropOldPending(DateTime now)
        {
            List<Pending> old = pending.FindAll(delegate (Pending p) { return !p.Queued && now - p.At > RetryFor; });
            if (old.Count == 0) return;
            List<string> nums = new List<string>();
            foreach (Pending p in old) { pending.Remove(p); nums.Add(p.Job.Number.ToString()); Log.Write("2분 넘게 못 보내 버림: " + p.Job.Action + " " + p.Job.Number); }
            Notify(Tone.Error, string.Join(", ", nums.ToArray()) + "번은 2분 넘게 못 보내 지웠습니다. 필요하면 다시 부르세요.");
            messageUntil = now.AddSeconds(60);
        }

        void OnPolled(CallsResult r, Exception ex)
        {
            if (r == null)
            {
                if (serverError == null) Log.Write("서버 연결 안 됨: " + ex.Message);
                serverError = ex.Message;
                fastPoll = true;
                if (DateTime.Now > messageUntil || lblMessage.ForeColor != Bad) { lblMessage.Text = ex.Message; lblMessage.ForeColor = Bad; messageUntil = DateTime.Now.AddSeconds(5); }
                Refresh2();
                return;
            }
            if (serverError != null) Log.Write("서버 다시 연결됨");
            serverError = null;
            if (pending.Count > 0) RetryPending();
            fastPoll = pending.Count > 0;
            lastServerOk = DateTime.Now;
            if (r.StoreName != null) storeName = r.StoreName;
            logic.SetOnScreen(r.Numbers, DateTime.Now);
            DrawNumbers(r.Numbers);
            Refresh2();
        }

        List<int> drawn = new List<int>();

        void DrawNumbers(List<int> list)
        {
            if (string.Join(",", list) == string.Join(",", drawn)) return;
            drawn = new List<int>(list);
            numbers.SuspendLayout();
            numbers.Controls.Clear();
            for (int i = 0; i < list.Count; i++)
            {
                int n = list[i];
                Button b = new Button();
                b.Text = n.ToString();
                b.Size = new Size(S(64), S(40));
                b.Font = new Font(Font.FontFamily, i == 0 ? 14f : 12f, FontStyle.Bold);
                b.FlatStyle = FlatStyle.Flat;
                b.BackColor = i == 0 ? Color.FromArgb(255, 236, 200) : Color.White;
                b.TabStop = false;
                b.Click += delegate { SelectNumber(selected == n ? -1 : n); };
                numbers.Controls.Add(b);
            }
            if (list.Count == 0)
            {
                Label none = new Label();
                none.Text = "없음";
                none.ForeColor = Color.DimGray;
                none.AutoSize = true;
                numbers.Controls.Add(none);
            }
            numbers.ResumeLayout();
            if (selected > 0 && !list.Contains(selected)) SelectNumber(-1);
        }

        void OpenSettings()
        {
            if (settingsOpen) return;
            settingsOpen = true; // 설정 창이 열린 동안은 숫자패드를 가로채지 않는다(칸에 숫자를 넣을 수 있게, 연결 확인 중 키보드가 멈추지 않게)
            hook.Uninstall();
            Refresh2();
            try
            {
                using (SettingsForm f = new SettingsForm(settings))
                {
                    DialogResult res = f.ShowDialog(this);
                    if (f.ExitRequested)
                    {
                        exitRequested = true;
                        ExitCode = Program.ExitByUser;
                        Close();
                        return;
                    }
                    if (res != DialogResult.OK) return;
                    settings = f.Result;
                    try { settings.Save(); }
                    catch (Exception ex) { Notify(Tone.Error, "설정을 저장하지 못했습니다: " + ex.Message); }
                    logic.FarGap = settings.FarGap;
                    TopMost = settings.AlwaysOnTop;
                    client = new BoardClient(settings.ServerUrl, settings.Key);
                    serverError = null;
                    lastServerOk = DateTime.MinValue;
                    ApplyCapture();
                    Refresh2();
                }
            }
            finally
            {
                settingsOpen = false;
                if (!exitRequested) ApplyCapture();
                Refresh2();
            }
        }

        protected override void OnResizeEnd(EventArgs e)
        {
            base.OnResizeEnd(e);
            if (WindowState != FormWindowState.Normal) return;
            settings.Left = Left;
            settings.Top = Top;
            try { settings.Save(); } catch (Exception) { }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing && !exitRequested)
            {
                e.Cancel = true; // 닫기 대신 최소화. 끝내려면 설정의 '앱 끝내기'
                ShowWindow(Handle, 7 /* SW_SHOWMINNOACTIVE */);
                return;
            }
            if (e.CloseReason == CloseReason.WindowsShutDown) ExitCode = Program.ExitByUser;
            stopping = true;
            hook.Dispose();
            jobs.CompleteAdding();
            base.OnFormClosing(e);
        }

        [DllImport("user32.dll")]
        static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        [DllImport("user32.dll")]
        static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    }
}
