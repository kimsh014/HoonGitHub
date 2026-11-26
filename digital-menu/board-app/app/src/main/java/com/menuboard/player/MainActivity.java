package com.menuboard.player;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.Process;
import android.text.TextUtils;
import android.util.Log;
import android.view.KeyEvent;
import android.view.PixelCopy;
import android.view.View;
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
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** 메뉴판 웹 화면을 전체 화면 WebView로 띄우는 플레이어. 홈 앱으로 지정하면 부팅 때 바로 뜬다. */
public class MainActivity extends Activity {
    private static final String TAG = "MenuBoard";
    private static final long SAVE_DELAY_MS = 3000; // rendered() 뒤 사진이 다 뜰 시간
    private static final long SAVE_GAP_MS = 10 * 60 * 1000; // 마지막 화면 저장은 10분에 한 번만(번호를 부를 때마다 쓰면 저장 장치가 닳는다)
    private static final long POLL_MS = 15000;      // 저장 화면을 띄운 동안 서버 확인 주기
    private static final long WATCH_MS = 30000;     // 실제 화면을 띄운 동안 서버 확인 주기
    private static final long LONG_PRESS_MS = 2000; // 리모컨 확인 버튼을 이만큼 누르면 설정 화면
    private static final int FIND_AFTER_FAILS = 4;  // 이만큼 연달아 실패하면 서버 주소가 바뀌었는지 망을 찾아본다
    private static final long FIND_EVERY_MS = 10 * 60 * 1000;
    private static final long UPDATE_CHECK_MS = 6 * 60 * 60 * 1000;
    private static final long REPORT_MS = 15000;    // TV 원격 관리: 매장 서버에 보고하고 할 일을 받는 주기

    private final Handler main = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private File archive;
    private FrameLayout root;
    private WebView web;
    private View dim;        // 밝기: 화면 위에 덮는 검은 막. HDMI TV는 앱이 백라이트를 못 바꾸므로 이 방법을 쓴다
    private BroadcastReceiver usbReceiver;
    private boolean reporting;
    private long lastArchive;
    private boolean offline; // 저장 화면 또는 "연결하는 중" 안내를 띄운 상태
    private boolean live;    // 실제 화면을 띄운 상태
    private boolean lost;    // 실제 화면을 띄운 뒤 서버 확인이 실패한 적이 있음 → 다시 붙으면 새로 불러온다
    private boolean resumed;
    private int fails;
    private long lastFind, lastUpdateCheck;
    private ConnectivityManager.NetworkCallback netCallback;

    private final Runnable poll = this::checkServer;
    private final Runnable longOk = this::openSettings;
    private final Runnable report = this::reportTick;
    private final Runnable checkUsb = this::checkUsb;
    private final Runnable adbDeadline = this::enforceAdb;

    // ponytail: 시간 지연만으로 사진 로드를 기다린다. 사진이 아주 많아 3초를 넘기면 일부가 빠진 채 저장될 수 있음 — 웹 화면이 사진 로드 완료 후 rendered()를 부르게 바꾸면 해결.
    private final Runnable saveArchive = () -> {
        if (!live || lost || web == null) return;
        File tmp = new File(getFilesDir(), "last.tmp.mht");
        // 임시 파일에 쓴 뒤 바꿔 넣어, 저장 도중 꺼져도 이전 화면이 깨지지 않게 한다
        lastArchive = System.currentTimeMillis();
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
        dim = new View(this);
        dim.setBackgroundColor(Color.BLACK);
        root.addView(dim, new FrameLayout.LayoutParams(-1, -1));
        root.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
            if (r - l != or - ol || b - t != ob - ot) v.post(this::applyLook); // HDMI 해상도가 바뀌면 회전 크기를 다시 맞춘다
        });
        applyIntent(getIntent());
        createWebView();
        registerNetwork();
        registerUsb();
        enforceAdb();
    }

    /** 와이파이·랜이 다시 잡히면 15~30초를 기다리지 않고 바로 서버를 확인한다. */
    private void registerNetwork() {
        ConnectivityManager cm = getSystemService(ConnectivityManager.class);
        if (cm == null) return;
        netCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network n) {
                main.post(() -> {
                    if (!resumed || server() == null) return;
                    Log.i(TAG, "네트워크 연결됨, 서버 확인");
                    main.removeCallbacks(poll);
                    main.postDelayed(poll, 2000); // 주소를 받을 틈을 준다
                });
            }
        };
        try {
            cm.registerDefaultNetworkCallback(netCallback);
        } catch (RuntimeException e) {
            netCallback = null;
            Log.w(TAG, "네트워크 알림 등록 실패, 주기 확인만 합니다", e);
        }
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
        resumed = true;
        applyLook();
        start();
        main.removeCallbacks(report);
        main.postDelayed(report, 3000);
        main.postDelayed(checkUsb, 1000);
    }

    /** 설정 화면 등을 띄운 동안에는 서버 확인을 멈춘다. */
    @Override
    protected void onPause() {
        super.onPause();
        resumed = false;
        main.removeCallbacks(poll);
        main.removeCallbacks(longOk);
        main.removeCallbacks(report);
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
        // WebView보다 먼저 가로챈다. 메뉴판 화면은 키 입력을 쓰지 않는다.
        switch (e.getKeyCode()) {
            case KeyEvent.KEYCODE_MENU:     // 키보드·일부 리모컨
            case KeyEvent.KEYCODE_SETTINGS: // 안드로이드 TV 리모컨의 설정(톱니) 버튼
                if (e.getAction() == KeyEvent.ACTION_UP) openSettings();
                return true;
            case KeyEvent.KEYCODE_DPAD_CENTER: // 리모컨 확인 버튼을 2초 누르면 설정
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_NUMPAD_ENTER:
                if (e.getAction() == KeyEvent.ACTION_DOWN && e.getRepeatCount() == 0) {
                    main.removeCallbacks(longOk);
                    main.postDelayed(longOk, LONG_PRESS_MS);
                } else if (e.getAction() == KeyEvent.ACTION_UP) {
                    main.removeCallbacks(longOk);
                }
                return true;
            default:
                return super.dispatchKeyEvent(e);
        }
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        // 뒤로 가기로 앱이 닫히지 않게 아무것도 하지 않는다
    }

    @Override
    protected void onDestroy() {
        main.removeCallbacksAndMessages(null);
        if (netCallback != null) getSystemService(ConnectivityManager.class).unregisterNetworkCallback(netCallback);
        if (usbReceiver != null) unregisterReceiver(usbReceiver);
        if (web != null) web.destroy();
        super.onDestroy();
    }

    private void openSettings() {
        main.removeCallbacks(longOk);
        startActivity(new Intent(this, SettingsActivity.class));
    }

    /** adb 등에서 --es server / --ei screen / --ei zoom 으로 넘긴 설정을 저장한다.
     *  이 화면은 홈 앱이라 다른 앱도 부를 수 있으므로, ADB가 켜져 있을 때(설치·A/S 중)만 받는다(점검표 R-7). */
    private boolean applyIntent(Intent i) {
        if (i == null || !i.hasExtra("server")) return false;
        if (android.provider.Settings.Global.getInt(getContentResolver(), android.provider.Settings.Global.ADB_ENABLED, 0) != 1) {
            Log.w(TAG, "ADB가 꺼져 있어 인텐트 설정 무시");
            return false;
        }
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
        SharedPreferences.Editor e = p.edit().putString("server", server.trim()).putInt("screen", sc).putInt("zoom", z);
        if (!server.trim().equals(p.getString("server", null))) e.remove("storeId"); // 다른 서버: 매장 번호는 다시 배운다
        e.apply();
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
                    live = false;
                    offline = false;
                    createWebView();
                    start();
                }
                return true;
            }
        });
        root.addView(web, 0, new FrameLayout.LayoutParams(-1, -1)); // 밝기 막(dim)보다 아래
        web.requestFocus();
        applyLook();
    }

    private void start() {
        main.removeCallbacks(poll);
        main.removeCallbacks(saveArchive);
        if (server() == null) {
            findFirstServer();
            return;
        }
        live = false; // 설정이 바뀌었을 수 있으니 실제 화면을 새로 불러온다
        checkServer();
    }

    /** 처음 켰을 때: 같은 망에서 메뉴판 서버를 찾아 하나뿐이면 바로 쓰고, 아니면 설정 화면을 연다. */
    private void findFirstServer() {
        showMessage("매장 서버를 찾는 중…", "리모컨 확인 버튼을 2초 누르면 설정 화면이 열립니다");
        new Thread(() -> {
            Map<String, String> found = Net.discover(this);
            main.post(() -> {
                if (!resumed) return;
                Map.Entry<String, String> one = found.size() == 1 ? found.entrySet().iterator().next() : null;
                if (one != null && save(prefs, one.getKey(), "1", "100") == null) {
                    prefs.edit().putString("storeId", one.getValue()).apply();
                    Log.i(TAG, "서버를 찾았습니다: " + one.getKey());
                    start();
                } else {
                    openSettings();
                }
            });
        }).start();
    }

    /**
     * /api/health 가 200이면 실제 주소를 (아직 안 띄웠거나 끊겼다 붙었으면) 다시 띄우고, 아니면 저장 화면을 띄운다.
     * 실제 화면을 띄운 동안에도 30초마다 확인한다. 끊긴 동안 웹 화면은 마지막 내용을 그대로 보여 준다.
     */
    private void checkServer() {
        String server = server();
        if (server == null) return;
        new Thread(() -> {
            boolean ok = Net.healthy(server);
            main.post(() -> onHealth(server, ok));
        }).start();
    }

    private void onHealth(String server, boolean ok) {
        if (!resumed || !server.equals(server())) return; // 그 사이 설정이 바뀌었거나 화면을 떠났다
        main.removeCallbacks(poll);
        if (ok) {
            fails = 0;
            if (!live || lost) {
                Log.i(TAG, lost ? "서버에 다시 연결됨, 화면을 새로 불러옵니다" : "서버 연결됨");
                offline = false;
                live = true;
                lost = false;
                web.loadUrl(liveUrl());
            }
            maybeCheckUpdate(server);
            learnStoreId(server);
            main.postDelayed(poll, WATCH_MS);
            return;
        }
        fails++;
        if (live) {
            lost = true; // 화면은 그대로 두고, 다시 붙으면 새로 불러온다
            main.postDelayed(poll, WATCH_MS / 2);
        } else if (!offline) {
            showOffline(); // 다음 확인을 스스로 예약한다
        } else {
            main.postDelayed(poll, POLL_MS);
        }
        maybeFindMovedServer(server);
    }

    /** 공유기를 바꾸거나 POS기 주소가 바뀐 경우: 오래 끊기면 같은 망에서 서버를 다시 찾는다. 하나만 찾았을 때만 바꾼다. */
    private void maybeFindMovedServer(String server) {
        long now = System.currentTimeMillis();
        if (fails < FIND_AFTER_FAILS || now - lastFind < FIND_EVERY_MS) return;
        lastFind = now;
        new Thread(() -> {
            Map<String, String> all = Net.discover(this);
            main.post(() -> {
                // 우리 매장 번호를 알면 같은 번호의 서버만 본다(공유기를 같이 쓰는 옆 가게 서버나 가짜 서버로 옮겨 가지 않게)
                String mine = prefs.getString("storeId", null);
                List<String> found = new ArrayList<>();
                for (Map.Entry<String, String> en : all.entrySet())
                    if (mine == null || mine.equals(en.getValue())) found.add(en.getKey());
                if (found.size() != 1 || found.get(0).equals(server) || !server.equals(server())) return;
                if (save(prefs, found.get(0), String.valueOf(prefs.getInt("screen", 1)),
                        String.valueOf(prefs.getInt("zoom", 100))) != null) return;
                if (mine != null) prefs.edit().putString("storeId", mine).apply();
                Log.i(TAG, "서버 주소가 바뀌었습니다: " + server + " → " + found.get(0));
                if (resumed) start();
            });
        }).start();
    }

    /** 붙은 서버의 매장 번호를 기억해 둔다. 서버를 다시 찾을 때 같은 매장 서버로만 옮기기 위해. */
    private void learnStoreId(String server) {
        if (prefs.getString("storeId", null) != null) return;
        new Thread(() -> {
            String id = Net.storeId(server, 3000);
            main.post(() -> {
                if (id != null && server.equals(server())) prefs.edit().putString("storeId", id).apply();
            });
        }).start();
    }

    /** 새 버전이 있는지만 확인해 둔다. 설치는 설정 화면에서 사람이 한다(손님 앞에서 확인 창이 뜨지 않게). */
    private void maybeCheckUpdate(String server) {
        long now = System.currentTimeMillis();
        if (now - lastUpdateCheck < UPDATE_CHECK_MS) return;
        lastUpdateCheck = now;
        new Thread(() -> Updater.check(this, server)).start();
    }

    private void showOffline() {
        offline = true;
        live = false;
        lost = false;
        if (archive.exists()) {
            web.loadUrl(Uri.fromFile(archive).toString());
        } else {
            showMessage("서버에 연결하는 중…", liveUrl());
        }
        main.removeCallbacks(poll);
        main.postDelayed(poll, POLL_MS);
    }

    private void showMessage(String title, String detail) {
        String html = "<html><body style='background:#000;color:#fff;font-family:sans-serif;"
                + "display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;margin:0'>"
                + "<h1 style='font-size:6vw'>" + TextUtils.htmlEncode(title) + "</h1>"
                + "<p style='font-size:3vw'>" + TextUtils.htmlEncode(detail) + "</p></body></html>";
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    // ── 화면 방향과 밝기 ──

    /**
     * 화면 방향(0/90/180/270)은 안드로이드 화면 회전 대신 WebView 자체를 돌려서 맞춘다.
     * 센서 없는 HDMI 보드·TV는 앱의 화면 방향 요청을 무시하는 경우가 많기 때문. 세로(90/270)면 웹 화면은 세로 크기로 그린다.
     */
    private void applyLook() {
        if (web == null || root.getWidth() == 0) return;
        int w = root.getWidth(), h = root.getHeight();
        int rot = prefs.getInt("rotation", 0);
        boolean portrait = rot == 90 || rot == 270;
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(portrait ? h : w, portrait ? w : h);
        web.setLayoutParams(lp);
        web.setPivotX(rot == 180 ? w / 2f : 0);
        web.setPivotY(rot == 180 ? h / 2f : 0);
        web.setRotation(rot);
        web.setTranslationX(rot == 90 ? w : 0);
        web.setTranslationY(rot == 270 ? h : 0);
        int b = prefs.getInt("brightness", -1); // -1 = 기본(덮지 않음)
        dim.setAlpha(b < 0 ? 0f : (100 - b) / 100f * 0.9f);
    }

    static String saveLook(SharedPreferences p, String rotation, String brightness) {
        int r, b;
        try {
            r = Integer.parseInt(rotation.trim());
            b = Integer.parseInt(brightness.trim());
        } catch (RuntimeException e) {
            return "화면 방향과 밝기는 숫자로 적어 주세요";
        }
        if (r != 0 && r != 90 && r != 180 && r != 270) return "화면 방향은 0, 90, 180, 270 중 하나입니다";
        if (b != -1 && (b < 10 || b > 100)) return "밝기는 10~100 이거나 -1(기본)입니다";
        p.edit().putInt("rotation", r).putInt("brightness", b).apply();
        return null;
    }

    // ── TV 원격 관리 (매장 서버의 관리 화면 devices.html) ──

    /** 15초마다: 지금 설정을 보고하고, 관리 화면에서 보낸 할 일을 받아 처리한다. 서버가 없어도 A/S 연결 마감은 지킨다. */
    private void reportTick() {
        main.removeCallbacks(report);
        enforceAdb();
        String server = server();
        if (!resumed || server == null || reporting) {
            if (resumed) main.postDelayed(report, REPORT_MS);
            return;
        }
        JSONObject reported = reported();
        reporting = true;
        new Thread(() -> {
            Remote.Orders o = Remote.report(this, server, reported);
            main.post(() -> {
                reporting = false;
                if (o != null && server.equals(server())) handleOrders(o, server);
                if (resumed) main.postDelayed(report, REPORT_MS);
            });
        }).start();
    }

    private JSONObject reported() {
        JSONObject j = new JSONObject();
        try {
            boolean canAdb = Remote.canAdb(this);
            Boolean adb = canAdb ? Remote.adbOn(this) : null;
            j.put("server", server()).put("screen", prefs.getInt("screen", 1)).put("zoom", prefs.getInt("zoom", 100))
                    .put("rotation", prefs.getInt("rotation", 0)).put("brightness", prefs.getInt("brightness", -1))
                    .put("adb", adb == null ? JSONObject.NULL : adb).put("canAdb", canAdb)
                    .put("rev", prefs.getInt("appliedRev", 0))
                    .put("usb", prefs.getString("usbResult", "")).put("note", prefs.getString("note", ""))
                    .put("width", root.getWidth()).put("height", root.getHeight());
        } catch (Exception ignored) {
            // put 은 숫자가 NaN 일 때만 실패한다
        }
        return j;
    }

    private void handleOrders(Remote.Orders o, String server) {
        // 등록 직후에는 그 전에 쌓인 재시작·캡처 요청을 따르지 않는다
        if (prefs.getInt("restartRev", -1) < 0) prefs.edit().putInt("restartRev", o.restartRev).commit();
        if (prefs.getInt("shotRev", -1) < 0) prefs.edit().putInt("shotRev", o.shotRev).commit();

        // A/S 연결: 서버가 닿으면 서버가 정한 마감을 따른다
        Remote.setAdbWindow(this, o.adbSeconds);
        enforceAdb();

        if (o.rev > prefs.getInt("appliedRev", 0)) applyDesired(o.desired, o.rev, server);
        if (o.shotRev > prefs.getInt("shotRev", 0)) {
            prefs.edit().putInt("shotRev", o.shotRev).commit();
            capture(server);
        }
        if (o.restartRev > prefs.getInt("restartRev", 0)) {
            prefs.edit().putInt("restartRev", o.restartRev).commit(); // 다시 켠 뒤 또 재시작하지 않게 먼저 적는다
            restartApp();
        }
    }

    /** 관리 화면에서 바꾼 설정. 보낸 칸만 바꾼다. 서버 주소는 새 주소에 실제로 붙어 본 뒤에만 바꾼다. */
    private void applyDesired(JSONObject d, int rev, String server) {
        prefs.edit().putInt("appliedRev", rev).putString("note", "").commit();
        String screen = String.valueOf(d.optInt("screen", prefs.getInt("screen", 1)));
        String zoom = String.valueOf(d.optInt("zoom", prefs.getInt("zoom", 100)));
        boolean reload = !screen.equals(String.valueOf(prefs.getInt("screen", 1)))
                || !zoom.equals(String.valueOf(prefs.getInt("zoom", 100)));
        String err = save(prefs, server, screen, zoom);
        String look = saveLook(prefs, String.valueOf(d.optInt("rotation", prefs.getInt("rotation", 0))),
                String.valueOf(d.optInt("brightness", prefs.getInt("brightness", -1))));
        if (err != null || look != null) prefs.edit().putString("note", err != null ? err : look).apply();
        applyLook();
        Log.i(TAG, "원격 설정 적용 (" + rev + ")");
        String next = d.optString("server", "");
        if (!next.isEmpty() && !next.equals(server)) {
            new Thread(() -> {
                boolean ok = Net.healthy(next);
                main.post(() -> {
                    if (ok && save(prefs, next, String.valueOf(prefs.getInt("screen", 1)),
                            String.valueOf(prefs.getInt("zoom", 100))) == null) {
                        Log.i(TAG, "원격으로 서버 주소 변경: " + next);
                        if (resumed) start();
                    } else {
                        prefs.edit().putString("note", "새 서버 주소 " + next + " 에 붙지 못해 그대로 둡니다").apply();
                    }
                });
            }).start();
        } else if (reload && resumed) {
            start();
        }
    }

    /** 지금 화면(창 전체, 돌린 모습 그대로)을 찍어 매장 서버에 올린다. */
    private void capture(String server) {
        View decor = getWindow().getDecorView();
        if (decor.getWidth() == 0) return;
        Bitmap bmp = Bitmap.createBitmap(decor.getWidth(), decor.getHeight(), Bitmap.Config.ARGB_8888);
        HandlerThread t = new HandlerThread("shot");
        t.start();
        PixelCopy.request(getWindow(), bmp, result -> {
            boolean ok = result == PixelCopy.SUCCESS && Remote.uploadShot(this, server, bmp);
            Log.i(TAG, "화면 캡처 " + (ok ? "올림" : "실패(" + result + ")"));
            bmp.recycle();
            t.quitSafely();
        }, new Handler(t.getLooper()));
    }

    /** 메뉴판 앱 다시 켜기(별도 프로세스의 RestartActivity 가 이 프로세스를 끝내고 다시 띄운다). */
    private void restartApp() {
        Log.i(TAG, "원격 요청으로 앱을 다시 켭니다");
        startActivity(new Intent(this, RestartActivity.class)
                .putExtra(RestartActivity.EXTRA_PID, Process.myPid())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
    }

    /** A/S 연결(ADB)은 마감 시각 전에만 켠다. 권한이 없으면 손대지 않는다. */
    private void enforceAdb() {
        long left = Remote.adbLeftMs(this);
        Remote.setAdb(this, left > 0);
        // 마감 때 꼭 잠근다. 설정 화면이 떠 있어 보고가 멈춘 동안에도(onPause 에서 지우지 않음)
        main.removeCallbacks(adbDeadline);
        if (left > 0) main.postDelayed(adbDeadline, left + 1000);
    }

    // ── USB 설정 파일 (현장 비상용) ──

    @SuppressWarnings("deprecation")
    private void registerUsb() {
        usbReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent i) {
                main.removeCallbacks(checkUsb);
                main.postDelayed(checkUsb, 1500); // 파일 시스템이 자리 잡을 틈
            }
        };
        IntentFilter f = new IntentFilter(Intent.ACTION_MEDIA_MOUNTED);
        f.addDataScheme("file");
        registerReceiver(usbReceiver, f);
    }

    private void checkUsb() {
        new Thread(() -> {
            File file = UsbConfig.find(this);
            if (file == null) return;
            Map<String, String> m;
            String hash;
            try {
                m = UsbConfig.read(file);
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                md.update(m.toString().getBytes("UTF-8"));
                hash = android.util.Base64.encodeToString(md.digest(), android.util.Base64.NO_WRAP);
            } catch (Exception e) {
                String why = UsbConfig.canRead() ? e.getMessage()
                        : "USB 파일을 읽을 권한이 없습니다. PC에서 install-board-app.bat 을 실행하세요";
                main.post(() -> {
                    if (why != null && !why.equals(prefs.getString("usbResult", ""))) {
                        prefs.edit().putString("usbResult", "실패: " + why).apply();
                        Toast.makeText(this, "USB 설정 파일 실패: " + why, Toast.LENGTH_LONG).show();
                    }
                });
                return;
            }
            main.post(() -> {
                if (hash.equals(prefs.getString("usbHash", ""))) return; // 이미 적용한 내용
                prefs.edit().putString("usbHash", hash).commit();
                applyUsb(m);
            });
        }).start();
    }

    private void applyUsb(Map<String, String> m) {
        List<String> done = new ArrayList<>(), errors = new ArrayList<>();
        String server = m.getOrDefault("server", server() == null ? "" : server());
        String err = save(prefs, server, m.getOrDefault("screen", String.valueOf(prefs.getInt("screen", 1))),
                m.getOrDefault("zoom", String.valueOf(prefs.getInt("zoom", 100))));
        if (m.containsKey("server") || m.containsKey("screen") || m.containsKey("zoom")) {
            if (err == null) done.add("서버·화면·배율"); else errors.add(err);
        }
        if (m.containsKey("rotation") || m.containsKey("brightness")) {
            String look = saveLook(prefs, m.getOrDefault("rotation", String.valueOf(prefs.getInt("rotation", 0))),
                    m.getOrDefault("brightness", String.valueOf(prefs.getInt("brightness", -1))));
            if (look == null) done.add("방향·밝기"); else errors.add(look);
        }
        if (m.containsKey("as")) {
            try {
                int min = Integer.parseInt(m.get("as"));
                if (min < 0 || min > Remote.MAX_ADB_MINUTES) throw new NumberFormatException();
                Remote.setAdbWindow(this, min * 60L);
                done.add(min == 0 ? "A/S 연결 잠금" : "A/S 연결 " + min + "분");
                if (!Remote.canAdb(this)) errors.add("A/S 연결 권한 없음(install-board-app.bat 필요)");
            } catch (NumberFormatException e) {
                errors.add("as 는 0~" + Remote.MAX_ADB_MINUTES + "(분)입니다");
            }
        }
        String msg = (done.isEmpty() ? "바뀐 것 없음" : String.join(", ", done) + " 적용")
                + (errors.isEmpty() ? "" : " / 틀린 곳: " + String.join(", ", errors));
        prefs.edit().putString("usbResult", msg).apply();
        Log.i(TAG, "USB 설정 파일: " + msg);
        Toast.makeText(this, "USB 설정 파일: " + msg, Toast.LENGTH_LONG).show();
        enforceAdb();
        applyLook();
        if ("yes".equalsIgnoreCase(m.get("restart"))) main.postDelayed(this::restartApp, 4000);
        else if (resumed) start();
    }

    /** 웹 화면이 window.MenuBoardHost.rendered() 로 부른다. */
    private class Host {
        @JavascriptInterface
        public void rendered() {
            // 저장이 이미 예약돼 있으면 그대로 둔다(그때 최신 화면이 저장된다)
            if (main.hasCallbacks(saveArchive)) return;
            long wait = Math.max(SAVE_DELAY_MS, lastArchive + SAVE_GAP_MS - System.currentTimeMillis());
            main.postDelayed(saveArchive, wait);
        }
    }
}
