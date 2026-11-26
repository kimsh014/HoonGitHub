// 키패드 입력을 번호 부르기·다시 부르기·취소로 바꾸는 부분. 화면·키보드·네트워크와 떨어져 있어 tests/에서 따로 검사한다.
// 키(숫자패드 기준):
//   숫자 + Enter      번호 부르기 (TV에 띄움)
//   +  [숫자] Enter   다시 부르기 (숫자를 빼면 TV 맨 앞 번호)
//   -  [숫자] Enter   TV에서 빼기 = 방금 완료 취소 (숫자를 빼면 TV 맨 앞 번호)
//   .                 한 자리 지움        *  /   입력 모두 지움
// 실수 막기(위험 점검표):
//   M-13·M-26  최근 번호와 많이 떨어진 번호, 이미 TV에 떠 있는 번호는 "Enter 한 번 더"로 확인
//   M-15       3초 안에 같은 번호를 또 부르면 한 번으로 침(서버도 한 번 더 막음)
//   입력하다 10초 손을 떼면 입력을 비움(어제 치다 만 숫자가 다음 번호 앞에 붙지 않게)
// C# 5 문법만 쓴다(Windows 10에 들어 있는 csc.exe로 빌드하므로).
using System;
using System.Collections.Generic;

namespace MenuBoardKeypad
{
    public enum PadKey { D0, D1, D2, D3, D4, D5, D6, D7, D8, D9, Enter, Dot, Plus, Minus, Star, Slash }

    public enum CallAction { Call, Recall, Cancel }

    public enum Tone { None, Info, Ok, Warn, Error }

    public sealed class Outcome
    {
        public bool Send;          // true면 서버에 보낸다
        public CallAction Action;
        public int Number;
        public string Message;     // 직원에게 보일 말(없으면 null)
        public Tone Tone;
    }

    public sealed class KeypadLogic
    {
        public const int MaxDigits = 4;
        public const int MaxNumber = 9999;
        public static readonly TimeSpan InputTimeout = TimeSpan.FromSeconds(10);
        public static readonly TimeSpan ConfirmTimeout = TimeSpan.FromSeconds(8);
        public static readonly TimeSpan SameCallWindow = TimeSpan.FromSeconds(3);
        static readonly TimeSpan HistoryKeep = TimeSpan.FromHours(4);
        const int HistoryCount = 5;

        // 최근 번호와 이만큼 넘게 떨어지면 확인을 받는다. 0이면 확인하지 않는다.
        public int FarGap = 30;

        string buffer = "";
        CallAction mode = CallAction.Call;
        DateTime lastKey = DateTime.MinValue;

        bool hasConfirm;
        CallAction confirmAction;
        int confirmNumber;
        DateTime confirmUntil;

        int lastSentNumber = -1;
        DateTime lastSentAt = DateTime.MinValue;

        List<int> onScreen = new List<int>();                       // 지금 TV에 떠 있는 번호, 최근 것부터
        List<KeyValuePair<int, DateTime>> history = new List<KeyValuePair<int, DateTime>>(); // 최근에 부른 번호(TV에서 빠진 뒤에도 기억)

        public string Buffer { get { return buffer; } }
        public CallAction Mode { get { return mode; } }
        public IList<int> OnScreen { get { return onScreen.AsReadOnly(); } }

        // 서버에서 받은 TV 번호 목록(최근 것부터)
        public void SetOnScreen(IList<int> numbers, DateTime now)
        {
            onScreen = new List<int>(numbers);
            for (int i = numbers.Count - 1; i >= 0; i--) Remember(numbers[i], now, false);
        }

        void Remember(int n, DateTime now, bool moveToFront)
        {
            int at = history.FindIndex(delegate (KeyValuePair<int, DateTime> h) { return h.Key == n; });
            if (at >= 0)
            {
                if (!moveToFront) return;
                history.RemoveAt(at);
            }
            history.Insert(0, new KeyValuePair<int, DateTime>(n, now));
            history.RemoveAll(delegate (KeyValuePair<int, DateTime> h) { return now - h.Value > HistoryKeep; });
            if (history.Count > HistoryCount) history.RemoveRange(HistoryCount, history.Count - HistoryCount);
        }

        // 화면에 보일 입력 줄. 예: "123", "다시 (12번)", "취소 7"
        public string InputText()
        {
            string label = mode == CallAction.Recall ? "다시 " : mode == CallAction.Cancel ? "취소 " : "";
            if (buffer.Length > 0) return label + buffer;
            if (mode == CallAction.Call) return "";
            return onScreen.Count > 0 ? label + "(" + onScreen[0] + "번)" : label;
        }

        // 1초마다 부른다. 입력이 오래 멈췄으면 비우고 true.
        public bool Tick(DateTime now)
        {
            if ((buffer.Length > 0 || mode != CallAction.Call) && now - lastKey > InputTimeout)
            {
                Reset();
                return true;
            }
            return false;
        }

        public void Reset()
        {
            buffer = "";
            mode = CallAction.Call;
            hasConfirm = false;
        }

        public Outcome Press(PadKey key, DateTime now)
        {
            if (now - lastKey > InputTimeout) Reset();
            lastKey = now;
            if (key <= PadKey.D9)
            {
                if (buffer.Length >= MaxDigits) return Say(Tone.Warn, "번호는 " + MaxDigits + "자리까지입니다. . 키로 지우세요.");
                buffer += ((int)key).ToString();
                hasConfirm = false;
                return Say(Tone.None, null);
            }
            switch (key)
            {
                case PadKey.Dot:
                    if (buffer.Length > 0) buffer = buffer.Substring(0, buffer.Length - 1);
                    else mode = CallAction.Call;
                    hasConfirm = false;
                    return Say(Tone.None, null);
                case PadKey.Star:
                case PadKey.Slash:
                    Reset();
                    return Say(Tone.Info, "입력을 지웠습니다.");
                case PadKey.Plus:
                    mode = CallAction.Recall;
                    hasConfirm = false;
                    return Say(Tone.Info, "다시 부를 번호 + Enter. 그냥 Enter면 " + FrontText() + "을 다시 부릅니다.");
                case PadKey.Minus:
                    mode = CallAction.Cancel;
                    hasConfirm = false;
                    return Say(Tone.Info, "TV에서 뺄 번호 + Enter. 그냥 Enter면 " + FrontText() + "을 뺍니다.");
                default:
                    return Enter(now);
            }
        }

        string FrontText()
        {
            return onScreen.Count > 0 ? "맨 앞 " + onScreen[0] + "번" : "맨 앞 번호";
        }

        Outcome Enter(DateTime now)
        {
            int n = 0;
            bool typed = buffer.Length > 0;
            if (typed) n = int.Parse(buffer);
            if (mode != CallAction.Call && !typed)
            {
                if (onScreen.Count == 0)
                {
                    Reset();
                    return Say(Tone.Warn, "TV에 떠 있는 번호가 없습니다.");
                }
                n = onScreen[0];
            }
            else if (!typed)
            {
                return Say(Tone.Info, "번호를 누르고 Enter를 누르세요.");
            }
            if (n < 1 || n > MaxNumber)
            {
                Reset();
                return Say(Tone.Warn, "번호는 1~" + MaxNumber + " 사이여야 합니다.");
            }

            if (mode == CallAction.Cancel)
            {
                if (!onScreen.Contains(n)) return Say(Tone.Warn, n + "번은 TV에 없습니다. 번호를 확인하세요.");
                return Send(CallAction.Cancel, n, now);
            }

            if (lastSentNumber == n && now - lastSentAt < SameCallWindow)
            {
                Reset();
                return Say(Tone.Info, n + "번은 방금 불렀습니다.");
            }
            if (mode == CallAction.Recall) return Send(CallAction.Recall, n, now);

            if (hasConfirm && confirmNumber == n && now <= confirmUntil) return Send(confirmAction, n, now);
            if (onScreen.Contains(n))
            {
                return Ask(CallAction.Recall, n, now, n + "번은 이미 TV에 떠 있습니다. 다시 부르려면 Enter를 한 번 더 누르세요.");
            }
            int near = FarFrom(n);
            if (near > 0)
            {
                return Ask(CallAction.Call, n, now, n + "번은 최근 번호(" + near + "번)와 많이 떨어져 있습니다. 맞으면 Enter 한 번 더, 틀리면 . 키로 고치세요.");
            }
            return Send(CallAction.Call, n, now);
        }

        // 최근 번호들과 모두 FarGap 넘게 떨어져 있으면 가장 최근 번호를, 아니면 0을 돌려준다.
        // 작은 번호(FarGap 이하)는 번호가 1부터 다시 시작한 것일 수 있어 묻지 않는다.
        int FarFrom(int n)
        {
            if (FarGap <= 0 || n <= FarGap || history.Count == 0) return 0;
            foreach (KeyValuePair<int, DateTime> h in history)
            {
                if (Math.Abs(h.Key - n) <= FarGap) return 0;
            }
            return history[0].Key;
        }

        Outcome Ask(CallAction action, int n, DateTime now, string message)
        {
            hasConfirm = true;
            confirmAction = action;
            confirmNumber = n;
            confirmUntil = now + ConfirmTimeout;
            return Say(Tone.Warn, message);
        }

        Outcome Send(CallAction action, int n, DateTime now)
        {
            Reset();
            if (action != CallAction.Cancel)
            {
                lastSentNumber = n;
                lastSentAt = now;
            }
            Outcome o = Say(Tone.Info, n + "번 " + (action == CallAction.Cancel ? "빼는" : "부르는") + " 중…");
            o.Send = true;
            o.Action = action;
            o.Number = n;
            return o;
        }

        // 서버에 못 보냈을 때: 입력을 되살려 Enter 한 번이면 다시 보내게 한다(확인은 다시 묻지 않음).
        public void SendFailed(CallAction action, int n, DateTime now)
        {
            buffer = n.ToString();
            mode = action == CallAction.Call ? CallAction.Call : action;
            lastSentNumber = -1;
            lastKey = now;
            hasConfirm = true;
            confirmAction = action;
            confirmNumber = n;
            confirmUntil = now + InputTimeout;
        }

        // 서버가 받았을 때. result: called | ignored | removed | absent
        public void SendDone(CallAction action, int n, string result, DateTime now)
        {
            if (action != CallAction.Cancel) Remember(n, now, true);
        }

        public static string ResultMessage(CallAction action, int n, string result)
        {
            switch (result)
            {
                case "called": return n + "번을 TV에 " + (action == CallAction.Recall ? "다시 " : "") + "띄웠습니다.";
                case "ignored": return n + "번은 방금 불러서 한 번만 띄웠습니다.";
                case "removed": return n + "번을 TV에서 뺐습니다.";
                case "absent": return n + "번은 이미 TV에 없습니다.";
                default: return n + "번: " + result;
            }
        }

        static Outcome Say(Tone tone, string message)
        {
            Outcome o = new Outcome();
            o.Tone = tone;
            o.Message = message;
            return o;
        }
    }
}
