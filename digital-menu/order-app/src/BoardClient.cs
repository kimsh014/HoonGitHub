// 매장 서버(PocketBase 메뉴판 서버)의 번호 호출 경로를 부른다. 연동 키(X-POS-Key)를 쓰므로 로그인 만료가 없다(B-12).
//   GET  /api/menuboard/pos/calls                       → { store: { id, name }, calls: [ { number, at } ] }
//   POST /api/menuboard/pos/calls { number, action }    → { number, action, result, calls }
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Web.Script.Serialization;

namespace MenuBoardKeypad
{
    public sealed class ServerException : Exception
    {
        public readonly int Status;
        public ServerException(int status, string message) : base(message) { Status = status; }
    }

    public sealed class CallsResult
    {
        public string StoreName;
        public List<int> Numbers = new List<int>(); // 최근 것부터
        public string Result;                       // 보냈을 때만: called | ignored | removed | absent
    }

    public sealed class BoardClient
    {
        public const int TimeoutMs = 4000;
        readonly string baseUrl;
        readonly string key;

        public BoardClient(string baseUrl, string key)
        {
            this.baseUrl = (baseUrl ?? "").Trim().TrimEnd('/');
            this.key = (key ?? "").Trim();
        }

        public CallsResult GetCalls()
        {
            return Parse(Request("GET", "/api/menuboard/pos/calls", null));
        }

        public CallsResult Send(CallAction action, int number)
        {
            string a = action == CallAction.Recall ? "recall" : action == CallAction.Cancel ? "cancel" : "call";
            return Parse(Request("POST", "/api/menuboard/pos/calls", "{\"number\":" + number + ",\"action\":\"" + a + "\"}"));
        }

        static CallsResult Parse(Dictionary<string, object> data)
        {
            CallsResult r = new CallsResult();
            object v;
            if (data.TryGetValue("store", out v) && v is Dictionary<string, object>)
            {
                object name;
                if (((Dictionary<string, object>)v).TryGetValue("name", out name)) r.StoreName = Convert.ToString(name);
            }
            if (data.TryGetValue("result", out v)) r.Result = Convert.ToString(v);
            if (data.TryGetValue("calls", out v) && v is IEnumerable)
            {
                foreach (object c in (IEnumerable)v)
                {
                    Dictionary<string, object> row = c as Dictionary<string, object>;
                    object n;
                    if (row != null && row.TryGetValue("number", out n)) r.Numbers.Add(Convert.ToInt32(n));
                }
            }
            return r;
        }

        Dictionary<string, object> Request(string method, string path, string body)
        {
            if (baseUrl.Length == 0) throw new ServerException(0, "서버 주소가 없습니다. 설정에서 넣어 주세요.");
            if (key.Length == 0) throw new ServerException(401, "연동 키가 없습니다. 설정에서 넣어 주세요.");
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(baseUrl + path);
            req.Method = method;
            req.Timeout = TimeoutMs;
            req.ReadWriteTimeout = TimeoutMs;
            req.Proxy = null; // 매장 안 서버라 시스템 프록시를 거치지 않는다
            req.KeepAlive = true;
            req.Headers["X-POS-Key"] = key;
            req.Accept = "application/json";
            try
            {
                if (body != null)
                {
                    byte[] bytes = Encoding.UTF8.GetBytes(body);
                    req.ContentType = "application/json";
                    req.ContentLength = bytes.Length;
                    using (Stream s = req.GetRequestStream()) s.Write(bytes, 0, bytes.Length);
                }
                using (HttpWebResponse res = (HttpWebResponse)req.GetResponse())
                {
                    return ReadJson(res);
                }
            }
            catch (WebException ex)
            {
                HttpWebResponse res = ex.Response as HttpWebResponse;
                if (res == null) throw new ServerException(0, "메뉴판 서버에 연결되지 않습니다. (" + ex.Status + ")");
                using (res)
                {
                    int status = (int)res.StatusCode;
                    string message = null;
                    try
                    {
                        object m;
                        if (ReadJson(res).TryGetValue("message", out m)) message = Convert.ToString(m);
                    }
                    catch (Exception) { }
                    if (status == 401) message = "연동 키가 맞지 않습니다. 수정 화면에서 키를 확인해 설정에 다시 넣어 주세요.";
                    else if (status == 404 && message == null) message = "서버가 번호 호출 기능을 모릅니다. 메뉴판 서버를 업데이트해 주세요.";
                    throw new ServerException(status, message ?? ("서버 오류 " + status));
                }
            }
        }

        static Dictionary<string, object> ReadJson(HttpWebResponse res)
        {
            using (StreamReader r = new StreamReader(res.GetResponseStream(), Encoding.UTF8))
            {
                string text = r.ReadToEnd();
                object o = new JavaScriptSerializer().DeserializeObject(text);
                Dictionary<string, object> d = o as Dictionary<string, object>;
                if (d == null) throw new ServerException(0, "서버 응답을 읽지 못했습니다.");
                return d;
            }
        }
    }
}
