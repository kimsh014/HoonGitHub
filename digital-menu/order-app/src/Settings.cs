// 설정과 기록. 설정은 %APPDATA%\MenuBoard\keypad.ini, 기록은 %LOCALAPPDATA%\MenuBoard\keypad.log.
// 연동 키는 Windows 데이터 보호(DPAPI, 현재 사용자)로 암호화해 둔다. 원문은 파일·기록에 남기지 않는다.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace MenuBoardKeypad
{
    public sealed class Settings
    {
        public string ServerUrl = "http://127.0.0.1:8090";
        public string Key = "";
        public bool CaptureNumpad = true;   // 숫자패드를 어느 창에서든 받아 판매 프로그램에는 안 보냄
        public bool AlwaysOnTop = true;
        public bool Sound = true;
        public int FarGap = 30;
        public int Left = int.MinValue, Top = int.MinValue;

        static readonly byte[] Entropy = Encoding.UTF8.GetBytes("MenuBoardKeypad.v1");

        public static string Folder
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "MenuBoard"); }
        }

        static string FilePath { get { return Path.Combine(Folder, "keypad.ini"); } }

        public static Settings Load()
        {
            Settings s = new Settings();
            try
            {
                if (!File.Exists(FilePath)) return s;
                foreach (string line in File.ReadAllLines(FilePath, Encoding.UTF8))
                {
                    int eq = line.IndexOf('=');
                    if (eq <= 0) continue;
                    string k = line.Substring(0, eq).Trim(), v = line.Substring(eq + 1).Trim();
                    int i;
                    switch (k)
                    {
                        case "server": s.ServerUrl = v; break;
                        case "key": s.Key = Unprotect(v); break;
                        case "capture": s.CaptureNumpad = v != "0"; break;
                        case "topmost": s.AlwaysOnTop = v != "0"; break;
                        case "sound": s.Sound = v != "0"; break;
                        case "fargap": if (int.TryParse(v, out i)) s.FarGap = Math.Max(0, Math.Min(9999, i)); break;
                        case "left": if (int.TryParse(v, out i)) s.Left = i; break;
                        case "top": if (int.TryParse(v, out i)) s.Top = i; break;
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Write("설정을 읽지 못함: " + ex.Message);
            }
            return s;
        }

        public void Save()
        {
            Directory.CreateDirectory(Folder);
            List<string> lines = new List<string>();
            lines.Add("# 메뉴판 키패드 앱 설정. key는 이 Windows 사용자만 풀 수 있게 암호화되어 있습니다.");
            lines.Add("server=" + ServerUrl);
            lines.Add("key=" + Protect(Key));
            lines.Add("capture=" + (CaptureNumpad ? "1" : "0"));
            lines.Add("topmost=" + (AlwaysOnTop ? "1" : "0"));
            lines.Add("sound=" + (Sound ? "1" : "0"));
            lines.Add("fargap=" + FarGap);
            if (Left != int.MinValue) { lines.Add("left=" + Left); lines.Add("top=" + Top); }
            string tmp = FilePath + ".tmp";
            File.WriteAllLines(tmp, lines.ToArray(), new UTF8Encoding(false));
            if (File.Exists(FilePath)) File.Replace(tmp, FilePath, null);
            else File.Move(tmp, FilePath);
        }

        static string Protect(string plain)
        {
            if (string.IsNullOrEmpty(plain)) return "";
            byte[] data = ProtectedData.Protect(Encoding.UTF8.GetBytes(plain), Entropy, DataProtectionScope.CurrentUser);
            return Convert.ToBase64String(data);
        }

        static string Unprotect(string stored)
        {
            if (string.IsNullOrEmpty(stored)) return "";
            try
            {
                return Encoding.UTF8.GetString(ProtectedData.Unprotect(Convert.FromBase64String(stored), Entropy, DataProtectionScope.CurrentUser));
            }
            catch (Exception)
            {
                Log.Write("저장된 연동 키를 풀지 못함(다른 Windows 사용자로 옮겨 왔을 수 있음). 설정에서 다시 넣어야 합니다.");
                return "";
            }
        }
    }

    public static class Log
    {
        static readonly object Gate = new object();
        const long MaxBytes = 1024 * 1024;

        public static string FilePath
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MenuBoard", "keypad.log"); }
        }

        // 1MB가 넘으면 keypad.log.1 로 옮긴다(최대 약 2MB).
        public static void Write(string text)
        {
            try
            {
                lock (Gate)
                {
                    string file = FilePath;
                    Directory.CreateDirectory(Path.GetDirectoryName(file));
                    FileInfo info = new FileInfo(file);
                    if (info.Exists && info.Length > MaxBytes)
                    {
                        string old = file + ".1";
                        if (File.Exists(old)) File.Delete(old);
                        File.Move(file, old);
                    }
                    File.AppendAllText(file, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + text + "\r\n", Encoding.UTF8);
                }
            }
            catch (Exception) { }
        }
    }
}
