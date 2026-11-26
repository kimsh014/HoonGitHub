// 숫자패드 키를 어느 창에 포커스가 있든 받는 저수준 키보드 훅(WH_KEYBOARD_LL).
// - 키를 가상 키 코드가 아니라 스캔 코드로 구별한다. 그래서 Num Lock이 꺼져 있어도(End·↓ 같은 키로 와도) 숫자로 읽는다(M-14).
// - 받은 키는 판매 프로그램에 넘기지 않는다(숫자가 판매 프로그램 입력칸에 새어 들어가지 않게).
// - 다른 프로그램(화상 키보드·자동 입력)이 만들어 낸 키, Alt를 누른 채 친 키(Alt+숫자 문자 입력, 일부 바코드 스캐너)는 건드리지 않는다.
// - Backspace는 숫자패드 키가 아니지만 키패드에 흔해서, 번호 창에 치던 것이 있을 때만 가져간다(handler가 정함).
// 한계: Windows 사용자 모드에서는 키를 '어느 키보드에서 왔는지'로 막을 수 없다. 숫자패드가 달린 일반 키보드를 판매
// 프로그램에 쓰는 매장은 설정에서 '숫자패드 가로채기'를 끄고 화면 단추로 부른다(docs/order-app.md).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace MenuBoardKeypad
{
    public sealed class NumpadHook : IDisposable
    {
        // true를 돌려주면 그 키를 삼킨다(다른 프로그램에 안 감)
        public delegate bool KeyHandler(PadKey key, bool repeat);

        const int WH_KEYBOARD_LL = 13;
        const int WM_KEYDOWN = 0x0100, WM_KEYUP = 0x0101, WM_SYSKEYDOWN = 0x0104, WM_SYSKEYUP = 0x0105;
        const uint LLKHF_EXTENDED = 0x01, LLKHF_INJECTED = 0x10;

        [StructLayout(LayoutKind.Sequential)]
        struct KBDLLHOOKSTRUCT { public uint vkCode; public uint scanCode; public uint flags; public uint time; public IntPtr dwExtraInfo; }

        delegate IntPtr HookProc(int nCode, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll", SetLastError = true)]
        static extern IntPtr SetWindowsHookEx(int idHook, HookProc lpfn, IntPtr hMod, uint dwThreadId);
        [DllImport("user32.dll", SetLastError = true)]
        static extern bool UnhookWindowsHookEx(IntPtr hhk);
        [DllImport("user32.dll")]
        static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")]
        static extern short GetAsyncKeyState(int vKey);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        static extern IntPtr GetModuleHandle(string name);

        readonly HookProc proc; // GC가 치우지 않게 붙들어 둔다
        readonly KeyHandler handler;
        readonly HashSet<uint> held = new HashSet<uint>(); // 삼킨 채 눌려 있는 키(뗄 때도 삼키고, 길게 누름 반복을 가려냄)
        IntPtr hook = IntPtr.Zero;

        public NumpadHook(KeyHandler handler)
        {
            this.handler = handler;
            proc = Callback;
        }

        public bool Installed { get { return hook != IntPtr.Zero; } }

        // 설치(이미 있으면 새로 건다). Windows는 응답이 늦은 훅을 말없이 떼어 버리기도 해서 1분마다 다시 건다.
        // 새 훅을 먼저 걸고 옛 훅을 떼므로 그 사이에 키가 판매 프로그램으로 새지 않는다.
        public void Install()
        {
            IntPtr fresh;
            using (Process me = Process.GetCurrentProcess())
            {
                fresh = SetWindowsHookEx(WH_KEYBOARD_LL, proc, GetModuleHandle(me.MainModule.ModuleName), 0);
            }
            if (fresh == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            IntPtr old = hook;
            hook = fresh;
            if (old != IntPtr.Zero) UnhookWindowsHookEx(old);
        }

        public void Uninstall()
        {
            if (hook != IntPtr.Zero) UnhookWindowsHookEx(hook);
            hook = IntPtr.Zero;
            held.Clear();
        }

        public void Dispose() { Uninstall(); }

        // 숫자패드 키의 스캔 코드(Num Lock과 상관없이 같다). extended는 Enter·/ 처럼 E0이 붙는 키.
        public static bool TryMap(uint scan, bool extended, out PadKey key)
        {
            key = PadKey.Enter;
            if (extended)
            {
                if (scan == 0x1C) { key = PadKey.Enter; return true; }
                if (scan == 0x35) { key = PadKey.Slash; return true; }
                return false; // 방향키·Home·End 등 따로 있는 키(E0)는 숫자패드가 아니다
            }
            switch (scan)
            {
                case 0x52: key = PadKey.D0; return true;
                case 0x4F: key = PadKey.D1; return true;
                case 0x50: key = PadKey.D2; return true;
                case 0x51: key = PadKey.D3; return true;
                case 0x4B: key = PadKey.D4; return true;
                case 0x4C: key = PadKey.D5; return true;
                case 0x4D: key = PadKey.D6; return true;
                case 0x47: key = PadKey.D7; return true;
                case 0x48: key = PadKey.D8; return true;
                case 0x49: key = PadKey.D9; return true;
                case 0x53: key = PadKey.Dot; return true;
                case 0x4A: key = PadKey.Minus; return true;
                case 0x4E: key = PadKey.Plus; return true;
                case 0x37: key = PadKey.Star; return true;
                case 0x0E: key = PadKey.Back; return true; // Backspace(키패드·일반 키보드 같음)
                default: return false; // Num Lock(0x45)은 그대로 둔다
            }
        }

        IntPtr Callback(int nCode, IntPtr wParam, IntPtr lParam)
        {
            try
            {
                if (nCode >= 0)
                {
                    KBDLLHOOKSTRUCT k = (KBDLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(KBDLLHOOKSTRUCT));
                    int msg = wParam.ToInt32();
                    bool down = msg == WM_KEYDOWN && (GetAsyncKeyState(0x12 /* VK_MENU */) & 0x8000) == 0; // Alt+숫자는 넘김
                    bool up = msg == WM_KEYUP || msg == WM_SYSKEYUP;
                    uint code = k.scanCode | ((k.flags & LLKHF_EXTENDED) != 0 ? 0x100u : 0u);
                    PadKey key;
                    if ((k.flags & LLKHF_INJECTED) == 0 && TryMap(k.scanCode, (k.flags & LLKHF_EXTENDED) != 0, out key))
                    {
                        if (down)
                        {
                            bool repeat = held.Contains(code);
                            if (handler(key, repeat)) { held.Add(code); return (IntPtr)1; }
                        }
                        else if (up && held.Remove(code))
                        {
                            return (IntPtr)1;
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Write("키보드 훅 오류: " + ex.Message); // 훅 안에서 예외가 나가면 키보드 전체가 멈출 수 있어 삼킨다
            }
            return CallNextHookEx(hook, nCode, wParam, lParam);
        }
    }
}
