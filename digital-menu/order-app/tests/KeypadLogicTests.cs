// KeypadLogic 검사. Windows: build.bat test  /  리눅스(mono): tests/run-tests.sh
using System;
using System.Collections.Generic;

namespace MenuBoardKeypad.Tests
{
    static class KeypadLogicTests
    {
        static int failed;
        static DateTime t0 = new DateTime(2026, 12, 1, 12, 0, 0);
        static DateTime now;

        static void Eq<T>(T actual, T expected, string what)
        {
            if (EqualityComparer<T>.Default.Equals(actual, expected)) return;
            failed++;
            Console.WriteLine("실패: " + what + " — 기대 " + expected + ", 실제 " + actual);
        }

        static void True(bool ok, string what)
        {
            if (ok) return;
            failed++;
            Console.WriteLine("실패: " + what);
        }

        static Outcome Type(KeypadLogic k, string keys)
        {
            Outcome last = null;
            foreach (char c in keys)
            {
                PadKey key;
                switch (c)
                {
                    case 'E': key = PadKey.Enter; break;
                    case '.': key = PadKey.Dot; break;
                    case '+': key = PadKey.Plus; break;
                    case '-': key = PadKey.Minus; break;
                    case '*': key = PadKey.Star; break;
                    default: key = (PadKey)(c - '0'); break;
                }
                now = now.AddMilliseconds(200);
                last = k.Press(key, now);
            }
            return last;
        }

        static void Sent(Outcome o, CallAction a, int n, string what)
        {
            True(o != null && o.Send, what + ": 보내야 함 (" + (o == null ? "null" : o.Message) + ")");
            if (o == null || !o.Send) return;
            Eq(o.Action, a, what + " 동작");
            Eq(o.Number, n, what + " 번호");
        }

        static void NotSent(Outcome o, string what)
        {
            True(o != null && !o.Send, what + ": 보내면 안 됨");
        }

        static KeypadLogic Fresh(params int[] onScreen)
        {
            now = t0;
            KeypadLogic k = new KeypadLogic();
            k.SetOnScreen(onScreen, now);
            return k;
        }

        static int Main()
        {
            try { Console.OutputEncoding = System.Text.Encoding.UTF8; } catch (Exception) { }
            KeypadLogic k = Fresh();
            Sent(Type(k, "12E"), CallAction.Call, 12, "번호+Enter");
            Eq(k.Buffer, "", "보낸 뒤 입력 비움");
            k.SendDone(CallAction.Call, 12, "called", now);
            k.SetOnScreen(new[] { 12 }, now);

            // M-15: 3초 안에 같은 번호
            NotSent(Type(k, "12E"), "3초 안 같은 번호");
            now = now.AddSeconds(4);
            Outcome o = Type(k, "12E");
            NotSent(o, "이미 TV에 있는 번호는 확인");
            True(o.Tone == Tone.Warn, "확인은 경고로");
            Sent(Type(k, "E"), CallAction.Recall, 12, "Enter 한 번 더 → 다시 부르기");

            // 지우기·고치기
            k = Fresh(12);
            Type(k, "123.");
            Eq(k.Buffer, "12", ". 한 자리 지움");
            Type(k, "*");
            Eq(k.Buffer, "", "* 모두 지움");
            NotSent(Type(k, "E"), "빈 Enter");
            NotSent(Type(k, "12345"), "다섯째 자리");
            Eq(k.Buffer, "1234", "4자리까지");
            Type(k, "*");
            NotSent(Type(k, "0E"), "0번");

            // M-13·M-26: 최근 번호와 멀리 떨어진 번호
            k = Fresh(101, 100);
            o = Type(k, "201E");
            NotSent(o, "멀리 떨어진 번호는 확인");
            True(o.Message.Contains("101"), "확인 문장에 최근 번호: " + o.Message);
            Sent(Type(k, "E"), CallAction.Call, 201, "한 번 더 Enter");
            k = Fresh(101, 100);
            Type(k, "201E");
            Type(k, "...");
            Sent(Type(k, "102E"), CallAction.Call, 102, "고쳐서 가까운 번호는 바로");
            k = Fresh(101, 100);
            Sent(Type(k, "125E"), CallAction.Call, 125, "30 안쪽은 바로");
            k = Fresh(998, 997);
            Sent(Type(k, "3E"), CallAction.Call, 3, "번호가 1부터 다시 시작(작은 번호)은 바로");
            k = Fresh();
            Sent(Type(k, "500E"), CallAction.Call, 500, "처음(최근 번호 없음)은 바로");
            k.SendDone(CallAction.Call, 500, "called", now);
            k.SetOnScreen(new int[0], now); // 10분 지나 TV에서 빠져도
            now = now.AddMinutes(11);
            NotSent(Type(k, "900E"), "TV에서 빠진 최근 번호와도 비교");
            k.FarGap = 0;
            Type(k, "*");
            Sent(Type(k, "900E"), CallAction.Call, 900, "기준 0이면 묻지 않음");

            // 확인은 8초 안에만
            k = Fresh(101);
            Type(k, "201E");
            now = now.AddSeconds(9);
            NotSent(Type(k, "E"), "8초 지나면 다시 물음");

            // M-14·M-26: 방금 완료 취소
            k = Fresh(15, 14);
            Eq(k.InputText(), "", "입력 없음");
            Type(k, "-");
            Eq(k.InputText(), "취소 (15번)", "빼기 미리 보기");
            Sent(Type(k, "E"), CallAction.Cancel, 15, "- Enter → 맨 앞 번호 빼기");
            Sent(Type(k, "-14E"), CallAction.Cancel, 14, "- 번호 Enter");
            NotSent(Type(k, "-99E"), "TV에 없는 번호는 빼지 않음");
            Type(k, "*");
            k = Fresh();
            NotSent(Type(k, "-E"), "TV가 비었으면 뺄 것 없음");

            // 다시 부르기
            k = Fresh(15, 14);
            Sent(Type(k, "+E"), CallAction.Recall, 15, "+ Enter → 맨 앞 다시");
            Sent(Type(k, "+14E"), CallAction.Recall, 14, "+ 번호 Enter");
            NotSent(Type(k, "+14E"), "3초 안 다시 부르기도 한 번");

            // 서버에 못 보냈을 때: Enter 한 번이면 다시 보냄(확인 다시 안 물음)
            k = Fresh(101);
            Type(k, "201E");
            o = Type(k, "E");
            Sent(o, CallAction.Call, 201, "확인 후 보냄");
            k.SendFailed(o.Action, o.Number, now);
            Eq(k.Buffer, "201", "실패하면 입력 되살림");
            Sent(Type(k, "E"), CallAction.Call, 201, "실패 후 Enter로 다시 보냄");

            // 10초 손 떼면 입력 비움
            k = Fresh();
            Type(k, "12");
            True(!k.Tick(now.AddSeconds(5)), "5초는 그대로");
            True(k.Tick(now.AddSeconds(11)), "10초 지나면 비움");
            Eq(k.Buffer, "", "비운 입력");
            Type(k, "-");
            now = now.AddSeconds(20);
            Sent(Type(k, "7E"), CallAction.Call, 7, "오래 지난 빼기 모드는 풀림");

            Eq(KeypadLogic.ResultMessage(CallAction.Call, 7, "called"), "7번을 TV에 띄웠습니다.", "결과 문장");

            if (failed == 0) Console.WriteLine("OK: 키패드 규칙(부르기·3초 중복·확인·빼기·다시·지우기·실패 후 다시 보내기·입력 시간 초과) 모두 맞습니다.");
            return failed == 0 ? 0 : 1;
        }
    }
}
