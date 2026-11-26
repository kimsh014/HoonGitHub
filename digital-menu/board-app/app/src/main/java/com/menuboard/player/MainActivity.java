package com.menuboard.player;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.Log;
import android.view.KeyEvent;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import java.io.File;
import java.net.HttpURLConnection;
import java.net.URL;

/** 메뉴판 웹 화면을 전체 화면 WebView로 띄우는 플레이어. 홈 앱으로 지정하면 부팅 때 바로 뜬다. */
public class MainActivity extends Activity {
    private static final String TAG = "MenuBoard";
    private static final long SAVE_DELAY_MS = 3000; // rendered() 뒤 사진이 다 뜰 시간
    private static final long POLL_MS = 15000;      // 저장 화면을 띄운 동안 서버 확인 주기

    private final Handler main = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private File archive;
    private FrameLayout root;
    private WebView web;
    private boolean offline; // 저장 화면 또는 "연결하는 중" 안내를 띄운 상태

    private final Runnable poll = this::checkServer;

    // ponytail: 시간 지연만으로 사진 로드를 기다린다. 사진이 아주 많아 3초를 넘기면 일부가 빠진 채 저장될 수 있음 — 웹 화면이 사진 로드 완료 후 rendered()를 부르게 바꾸면 해결.
    private final Runnable saveArchive = () -> {
        if (offline || web == null) return;
        File tmp = new File(getFilesDir(), "last.tmp.mht");
        // 임시 파일에 쓴 뒤 바꿔 넣어, 저장 도중 꺼져도 이전 화면이 깨지지 않게 한다
        web.saveWebArchive(tmp.getPath(), false, path -> {
            if (path != null && tmp.renameTo(archive)) Log.i(TAG, "마지막 화면 저장: " + archive);
        });
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("board", MODE_PRIVATE);
        archive = new File(getFilesDir(), "last.mht");
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getAttributes().layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        setContentView(root);
        applyIntent(getIntent());
        createWebView();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyIntent(intent); // 홈 키 등 값 없는 인텐트는 무시. 이어서 onResume이 다시 띄운다
    }

    /** 처음 켤 때, 인텐트를 받은 뒤, 설정 화면·안드로이드 설정에서 돌아올 때 최신 설정으로 다시 띄운다. */
    @Override
    protected void onResume() {
        super.onResume();
        start();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (!hasFocus) return;
        getWindow().setDecorFitsSystemWindows(false);
        WindowInsetsController c = getWindow().getInsetsController();
        c.hide(WindowInsets.Type.systemBars());
        c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        // WebView보다 먼저 가로챈다: 키보드·리모컨 MENU 키로 설정 열기
        if (e.getKeyCode() == KeyEvent.KEYCODE_MENU) {
            if (e.getAction() == KeyEvent.ACTION_UP) openSettings();
            return true;
        }
        return super.dispatchKeyEvent(e);
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        // 뒤로 가기로 앱이 닫히지 않게 아무것도 하지 않는다
    }

    @Override
    protected void onDestroy() {
        main.removeCallbacksAndMessages(null);
        if (web != null) web.destroy();
        super.onDestroy();
    }

    private void openSettings() {
        startActivity(new Intent(this, SettingsActivity.class));
    }

    /** adb 등에서 --es server / --ei screen / --ei zoom 으로 넘긴 설정을 저장한다. */
    private boolean applyIntent(Intent i) {
        if (i == null || !i.hasExtra("server")) return false;
        String err = save(prefs, i.getStringExtra("server"),
                String.valueOf(i.getIntExtra("screen", 1)), String.valueOf(i.getIntExtra("zoom", 100)));
        if (err != null) Log.w(TAG, "인텐트 설정 무시: " + err);
        return err == null;
    }

    /** 설정 검사 후 저장. 문제가 있으면 안내 문구를, 저장했으면 null을 돌려준다. */
    static String save(SharedPreferences p, String server, String screen, String zoom) {
        int sc, z;
        try {
            sc = Integer.parseInt(screen.trim());
            z = Integer.parseInt(zoom.trim());
        } catch (RuntimeException e) {
            return "화면 번호와 배율은 숫자로 적어 주세요";
        }
        if (server == null || !server.trim().matches("[A-Za-z0-9.-]+(:[0-9]{1,5})?"))
            return "서버 주소는 192.168.0.10:8090 형식으로 적어 주세요";
        if (sc < 1 || sc > 4) return "화면 번호는 1~4 입니다";
        if (z < 25 || z > 400) return "배율은 25~400% 입니다";
        p.edit().putString("server", server.trim()).putInt("screen", sc).putInt("zoom", z).apply();
        return null;
    }

    private String server() {
        return prefs.getString("server", null);
    }

    private String liveUrl() {
        return "http://" + server() + "/?screen=" + prefs.getInt("screen", 1) + "&zoom=" + prefs.getInt("zoom", 100);
    }

    private void createWebView() {
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);       // 저장해 둔 화면(file://...mht)을 띄우기 위해. API 30+ 기본값은 false
        s.setUseWideViewPort(true);       // 웹 화면의 viewport meta를 따른다
        s.setLoadWithOverviewMode(true);  // viewport meta가 없으면 화면 너비에 맞춘다
        s.setSupportZoom(false);
        s.setTextZoom(100);               // 글자 배율은 주소의 zoom 값으로만 정한다(시스템 글꼴 크기 무시)
        web.setBackgroundColor(Color.BLACK);
        web.addJavascriptInterface(new Host(), "MenuBoardHost");
        web.setOnLongClickListener(v -> { openSettings(); return true; });     // 길게 누르기
        web.setOnContextClickListener(v -> { openSettings(); return true; });  // 마우스 오른쪽 클릭
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                // 페이지 자체 로드 실패만 본다. 실제 화면을 띄운 뒤의 요청 실패는 웹 화면이 스스로 처리한다
                // ponytail: 연결 실패만 잡고 HTTP 오류 응답(500 등)은 그대로 띄운다. /api/health 가 200인데 첫 화면만 오류인 경우가 생기면 onReceivedHttpError 에서도 showOffline() 하면 된다.
                if (r.isForMainFrame() && !offline) {
                    Log.w(TAG, "페이지 로드 실패: " + e.getDescription());
                    showOffline();
                }
            }

            @Override
            public boolean onRenderProcessGone(WebView v, RenderProcessGoneDetail d) {
                // 24시간 장비: 렌더러가 죽어도 앱은 살아남아 화면을 새로 만든다
                Log.e(TAG, "WebView 렌더러 종료(crash=" + d.didCrash() + "), 다시 만듭니다");
                root.removeView(v);
                v.destroy();
                if (v == web) {
                    createWebView();
                    start();
                }
                return true;
            }
        });
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        web.requestFocus();
    }

    private void start() {
        main.removeCallbacks(poll);
        main.removeCallbacks(saveArchive);
        if (server() == null) {
            openSettings();
            return;
        }
        checkServer();
    }

    /** /api/health 가 200이면 실제 주소를, 아니면 저장 화면을 띄운다. */
    private void checkServer() {
        String health = "http://" + server() + "/api/health";
        new Thread(() -> {
            boolean ok;
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(health).openConnection();
                c.setConnectTimeout(3000);
                c.setReadTimeout(3000);
                ok = c.getResponseCode() == 200;
                c.disconnect();
            } catch (Exception e) {
                ok = false;
            }
            boolean alive = ok;
            main.post(() -> {
                if (alive) {
                    offline = false;
                    web.loadUrl(liveUrl());
                } else if (!offline) {
                    showOffline();
                } else {
                    main.postDelayed(poll, POLL_MS);
                }
            });
        }).start();
    }

    private void showOffline() {
        offline = true;
        if (archive.exists()) {
            web.loadUrl(Uri.fromFile(archive).toString());
        } else {
            String html = "<html><body style='background:#000;color:#fff;font-family:sans-serif;"
                    + "display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;margin:0'>"
                    + "<h1 style='font-size:6vw'>서버에 연결하는 중…</h1>"
                    + "<p style='font-size:3vw'>" + TextUtils.htmlEncode(liveUrl()) + "</p></body></html>";
            web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
        }
        main.removeCallbacks(poll);
        main.postDelayed(poll, POLL_MS);
    }

    /** 웹 화면이 window.MenuBoardHost.rendered() 로 부른다. */
    private class Host {
        @JavascriptInterface
        public void rendered() {
            main.removeCallbacks(saveArchive);
            main.postDelayed(saveArchive, SAVE_DELAY_MS);
        }
    }
}
