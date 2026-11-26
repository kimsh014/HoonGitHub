// 메뉴판 키패드 앱(MenuBoardKeypad.exe) 시작점.
//   MenuBoardKeypad.exe        지킴이: 창 없이 떠서 앱을 켜고, 앱이 비정상으로 꺼지면 2초 뒤 다시 켠다(M-16).
//                              작업 스케줄러가 Windows 로그인 때 이것을 실행한다(install-order-app.bat).
//   MenuBoardKeypad.exe --app  앱 본체(번호 창). 직원이 설정의 '앱 끝내기'로 닫을 때만 종료 코드 0으로 끝나고 지킴이도 멈춘다.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Windows.Forms;

namespace MenuBoardKeypad
{
    static class Program
    {
        public const string Version = "0.1.0";
        public const int ExitByUser = 0;

        [STAThread]
        static int Main(string[] args)
        {
            bool app = Array.IndexOf(args, "--app") >= 0;
            return app ? RunApp() : RunGuard();
        }

        static int RunApp()
        {
            bool created;
            using (Mutex one = new Mutex(true, @"Local\MenuBoardKeypadApp", out created))
            {
                if (!created) return ExitByUser; // 이미 떠 있다
                Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
                Application.ThreadException += delegate (object s, ThreadExceptionEventArgs e) { Crash(e.Exception); };
                AppDomain.CurrentDomain.UnhandledException += delegate (object s, UnhandledExceptionEventArgs e) { Crash(e.ExceptionObject as Exception); };
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Log.Write("앱 시작 v" + Version);
                MainForm form = new MainForm();
                Application.Run(form);
                Log.Write("앱 끝 (" + form.ExitCode + ")");
                return form.ExitCode;
            }
        }

        static void Crash(Exception ex)
        {
            Log.Write("앱 오류로 끝남: " + ex);
            Environment.Exit(1); // 지킴이가 다시 켠다
        }

        static int RunGuard()
        {
            bool created;
            using (Mutex one = new Mutex(true, @"Local\MenuBoardKeypadGuard", out created))
            {
                if (!created) return 0;
                string exe = Process.GetCurrentProcess().MainModule.FileName;
                Queue<DateTime> starts = new Queue<DateTime>();
                while (true)
                {
                    // 1분 안에 5번 넘게 죽으면 30초 쉬었다 켠다(망가진 상태로 CPU를 먹지 않게).
                    while (starts.Count > 0 && DateTime.Now - starts.Peek() > TimeSpan.FromMinutes(1)) starts.Dequeue();
                    if (starts.Count >= 5)
                    {
                        Log.Write("앱이 1분 안에 5번 꺼져 30초 쉽니다.");
                        Thread.Sleep(30000);
                        starts.Clear();
                    }
                    starts.Enqueue(DateTime.Now);
                    int code;
                    try
                    {
                        using (Process p = Process.Start(new ProcessStartInfo(exe, "--app") { UseShellExecute = false }))
                        {
                            p.WaitForExit();
                            code = p.ExitCode;
                        }
                    }
                    catch (Exception ex)
                    {
                        Log.Write("앱을 켜지 못함: " + ex.Message);
                        code = -1;
                    }
                    if (code == ExitByUser) return 0;
                    Log.Write("앱이 꺼져(" + code + ") 2초 뒤 다시 켭니다.");
                    Thread.Sleep(2000);
                }
            }
        }
    }
}
