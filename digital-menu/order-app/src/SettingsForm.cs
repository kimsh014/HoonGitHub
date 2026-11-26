// 설정 창: 서버 주소, 연동 키, 숫자패드 가로채기, 항상 위, 소리, 멀리 떨어진 번호 확인 기준, 연결 확인, 앱 끝내기.
using System;
using System.Drawing;
using System.Windows.Forms;

namespace MenuBoardKeypad
{
    public sealed class SettingsForm : Form
    {
        public Settings Result;
        public bool ExitRequested;

        readonly Settings old;
        TextBox txtServer, txtKey;
        CheckBox chkCapture, chkTop, chkSound;
        NumericUpDown numGap;
        Label lblTest;

        public SettingsForm(Settings current)
        {
            old = current;
            Text = "번호 호출 설정";
            Font = new Font("Malgun Gothic", 10f);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            TopMost = true;
            AutoSize = true;
            AutoSizeMode = AutoSizeMode.GrowAndShrink;
            Padding = new Padding(12);

            TableLayoutPanel t = new TableLayoutPanel();
            t.AutoSize = true;
            t.ColumnCount = 2;
            t.Dock = DockStyle.Fill;
            Controls.Add(t);

            txtServer = new TextBox();
            txtServer.Width = 340;
            txtServer.Text = current.ServerUrl;
            Row(t, "메뉴판 서버 주소", txtServer);
            Row(t, "", Hint("이 POS기에 서버가 있으면 http://127.0.0.1:8090 그대로 둡니다."));

            txtKey = new TextBox();
            txtKey.Width = 340;
            txtKey.UseSystemPasswordChar = true;
            Row(t, "POS 연동 키", txtKey);
            Row(t, "", Hint(current.Key.Length > 0
                ? "저장된 키가 있습니다. 바꿀 때만 새 키(mbpos_…)를 붙여 넣으세요."
                : "수정 화면(admin.html) 맨 아래 'POS·키오스크 연동'의 키(mbpos_…)를 붙여 넣으세요.\n키오스크에 이미 쓰는 키가 있으면 같은 키를 넣습니다(새로 만들면 예전 키가 막힘)."));

            chkCapture = Check(t, "숫자패드 키를 이 앱이 받기 (판매 프로그램에는 안 감)", current.CaptureNumpad);
            Row(t, "", Hint("판매 프로그램에 숫자패드를 써야 하는 매장은 끄고 화면 단추로 부릅니다."));
            chkTop = Check(t, "항상 위에 두기", current.AlwaysOnTop);
            chkSound = Check(t, "소리 (부름·경고)", current.Sound);

            numGap = new NumericUpDown();
            numGap.Minimum = 0;
            numGap.Maximum = 9999;
            numGap.Width = 80;
            numGap.Value = current.FarGap;
            Row(t, "멀리 떨어진 번호 확인", numGap);
            Row(t, "", Hint("최근 번호와 이만큼 넘게 차이 나면 Enter를 한 번 더 받습니다. 0이면 묻지 않습니다."));

            Button test = new Button();
            test.Text = "연결 확인";
            test.AutoSize = true;
            test.Click += delegate { TestConnection(); };
            lblTest = new Label();
            lblTest.AutoSize = true;
            lblTest.MaximumSize = new Size(360, 0);
            FlowLayoutPanel testRow = new FlowLayoutPanel();
            testRow.AutoSize = true;
            testRow.Controls.Add(test);
            testRow.Controls.Add(lblTest);
            Row(t, "", testRow);

            Button save = new Button();
            save.Text = "저장";
            save.AutoSize = true;
            save.Click += delegate { if (Collect()) { DialogResult = DialogResult.OK; Close(); } };
            Button cancel = new Button();
            cancel.Text = "취소";
            cancel.AutoSize = true;
            cancel.DialogResult = DialogResult.Cancel;
            Button exit = new Button();
            exit.Text = "앱 끝내기";
            exit.AutoSize = true;
            exit.ForeColor = Color.FromArgb(200, 30, 30);
            exit.Click += delegate { AskExit(); };
            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.AutoSize = true;
            buttons.Controls.Add(save);
            buttons.Controls.Add(cancel);
            buttons.Controls.Add(exit);
            Row(t, "", buttons);
            Row(t, "", Hint("버전 " + Program.Version + " · 기록: " + Log.FilePath));
            AcceptButton = save;
            CancelButton = cancel;
        }

        static Label Hint(string text)
        {
            Label l = new Label();
            l.Text = text;
            l.AutoSize = true;
            l.MaximumSize = new Size(360, 0);
            l.ForeColor = Color.DimGray;
            l.Font = new Font("Malgun Gothic", 8.5f);
            return l;
        }

        static void Row(TableLayoutPanel t, string label, Control c)
        {
            Label l = new Label();
            l.Text = label;
            l.AutoSize = true;
            l.Anchor = AnchorStyles.Left;
            t.Controls.Add(l);
            t.Controls.Add(c);
        }

        static CheckBox Check(TableLayoutPanel t, string text, bool value)
        {
            CheckBox c = new CheckBox();
            c.Text = text;
            c.AutoSize = true;
            c.Checked = value;
            Row(t, "", c);
            return c;
        }

        string KeyToUse()
        {
            string k = txtKey.Text.Trim();
            return k.Length > 0 ? k : old.Key;
        }

        bool Collect()
        {
            string url = txtServer.Text.Trim().TrimEnd('/');
            Uri u;
            if (!Uri.TryCreate(url, UriKind.Absolute, out u) || (u.Scheme != "http" && u.Scheme != "https"))
            {
                MessageBox.Show(this, "서버 주소는 http://로 시작해야 합니다. 예: http://127.0.0.1:8090", Text);
                return false;
            }
            string key = KeyToUse();
            if (key.Length > 0 && !key.StartsWith("mbpos_"))
            {
                MessageBox.Show(this, "연동 키는 mbpos_ 로 시작합니다. 수정 화면에서 복사한 키를 그대로 붙여 넣으세요.", Text);
                return false;
            }
            Result = new Settings();
            Result.ServerUrl = url;
            Result.Key = key;
            Result.CaptureNumpad = chkCapture.Checked;
            Result.AlwaysOnTop = chkTop.Checked;
            Result.Sound = chkSound.Checked;
            Result.FarGap = (int)numGap.Value;
            Result.Left = old.Left;
            Result.Top = old.Top;
            return true;
        }

        void TestConnection()
        {
            lblTest.ForeColor = Color.Black;
            lblTest.Text = "확인 중…";
            lblTest.Refresh();
            Cursor = Cursors.WaitCursor;
            try
            {
                CallsResult r = new BoardClient(txtServer.Text, KeyToUse()).GetCalls();
                lblTest.ForeColor = Color.FromArgb(20, 130, 60);
                lblTest.Text = "연결됨: " + r.StoreName + " (TV 번호 " + r.Numbers.Count + "개)";
            }
            catch (Exception ex)
            {
                lblTest.ForeColor = Color.FromArgb(200, 30, 30);
                lblTest.Text = ex.Message;
            }
            finally { Cursor = Cursors.Default; }
        }

        void AskExit()
        {
            DialogResult r = MessageBox.Show(this,
                "앱을 끝내면 키패드로 번호를 부를 수 없습니다.\n다음에 Windows에 로그인하면 다시 켜집니다.\n\n끝낼까요?",
                Text, MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
            if (r != DialogResult.Yes) return;
            ExitRequested = true;
            DialogResult = DialogResult.Cancel;
            Close();
        }
    }
}
