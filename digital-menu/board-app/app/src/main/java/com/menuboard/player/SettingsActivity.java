package com.menuboard.player;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.util.TypedValue;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

/**
 * 서버 주소·화면 번호·글자 배율 설정과 업데이트·권한 버튼.
 * 안드로이드 TV 리모컨(방향키+확인)만으로 움직일 수 있게 기본 위젯만 쓰고 글자를 크게 한다.
 */
public class SettingsActivity extends Activity {
    private SharedPreferences prefs;
    private EditText server, screen, zoom, rotation, brightness;
    private TextView status;
    private Button overlay, unknown;

    // 리모컨 확인 버튼을 실수로 2초 눌러 열린 경우, 손님 앞에 설정 화면이 계속 떠 있지 않게 2분 동안 손대지 않으면 메뉴판으로 돌아간다
    private static final long IDLE_MS = 2 * 60 * 1000;
    private final Handler idle = new Handler(Looper.getMainLooper());
    private final Runnable leave = this::leaveIfIdle;
    private boolean busy; // 업데이트를 받는 중에는 닫지 않는다

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("board", MODE_PRIVATE);
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(64, 32, 64, 32);

        text(l, "메뉴판 보드 설정  ·  버전 " + Updater.installedName(this) + " (" + Updater.installedCode(this) + ")", 26);
        text(l, "메뉴판 화면에서 리모컨 확인 버튼을 2초 누르면 이 화면이 열립니다.", 18);

        server = field(l, "서버 주소 (POS기, 예: 192.168.0.10:8090)", prefs.getString("server", ""),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        screen = field(l, "화면 번호 (1~4)", String.valueOf(prefs.getInt("screen", 1)), InputType.TYPE_CLASS_NUMBER);
        zoom = field(l, "글자 크기 배율 (%)", String.valueOf(prefs.getInt("zoom", 100)), InputType.TYPE_CLASS_NUMBER);

        Button save = button(l, "저장하고 메뉴판 보기", v -> {
            String err = MainActivity.save(prefs, server.getText().toString(),
                    screen.getText().toString(), zoom.getText().toString());
            if (err == null) err = MainActivity.saveLook(prefs, rotation.getText().toString(), brightness.getText().toString());
            if (err != null) toast(err);
            else finish();
        });
        button(l, "같은 망에서 서버 자동 찾기", v -> find());
        button(l, "업데이트 확인·설치", v -> update());
        status = text(l, "", 18);
        String usb = prefs.getString("usbResult", "");
        String adb = Remote.canAdb(this) ? (Boolean.TRUE.equals(Remote.adbOn(this)) ? "열림" : "잠금") : "권한 없음(설치 bat 필요)";
        text(l, "A/S 연결(ADB): " + adb + (usb.isEmpty() ? "" : "   ·   USB 설정 파일: " + usb), 16);

        overlay = button(l, "부팅 때 자동 실행 허용 (다른 앱 위에 표시)", v -> open(
                new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()))));
        unknown = button(l, "업데이트 설치 허용 (출처를 알 수 없는 앱)", v -> open(
                new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName()))));
        // 이 앱이 홈 앱이면 와이파이 설정 등으로 나갈 길이 여기뿐이다
        button(l, "안드로이드 설정 열기 (와이파이 등)", v -> open(new Intent(Settings.ACTION_SETTINGS)));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(l);
        setContentView(scroll);
        // 리모컨으로 바로 움직일 수 있게: 주소가 있으면 저장 버튼, 없으면 주소 칸에서 시작
        (prefs.getString("server", null) == null ? server : save).requestFocus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        resetIdle();
        // 권한 화면에서 돌아오면 이미 허용된 버튼은 숨긴다
        overlay.setVisibility(Settings.canDrawOverlays(this) ? View.GONE : View.VISIBLE);
        unknown.setVisibility(getPackageManager().canRequestPackageInstalls() ? View.GONE : View.VISIBLE);
        String up = prefs.getString("updateName", null);
        if (up != null && status.getText().length() == 0) status.setText("새 버전이 있습니다: " + up);
    }

    private void find() {
        status.setText("같은 망에서 메뉴판 서버를 찾는 중… (최대 30초)");
        new Thread(() -> {
            List<String> found = new ArrayList<>(Net.discover(this).keySet());
            runOnUiThread(() -> {
                if (found.isEmpty()) {
                    status.setText("서버를 찾지 못했습니다. POS기에서 메뉴판 서버가 켜져 있는지, 같은 공유기에 연결됐는지 확인하세요.");
                } else {
                    server.setText(found.get(0));
                    status.setText(found.size() == 1 ? "서버를 찾았습니다: " + found.get(0) + "  → 저장을 누르세요"
                            : "서버가 여러 대입니다: " + String.join(", ", found) + "  → 맞는 주소로 고친 뒤 저장하세요");
                }
            });
        }).start();
    }

    @Override
    protected void onPause() {
        super.onPause();
        idle.removeCallbacks(leave);
    }

    @Override
    public void onUserInteraction() {
        super.onUserInteraction();
        resetIdle();
    }

    private void resetIdle() {
        idle.removeCallbacks(leave);
        idle.postDelayed(leave, IDLE_MS);
    }

    private void leaveIfIdle() {
        if (busy) resetIdle();
        else finish();
    }

    private void update() {
        String s = prefs.getString("server", null);
        if (s == null) {
            toast("서버 주소를 먼저 저장하세요");
            return;
        }
        status.setText("업데이트 확인 중…");
        busy = true;
        new Thread(() -> {
            Updater.Info info = Updater.check(this, s);
            String msg;
            if (info == null) msg = "서버에 올라온 업데이트가 없습니다";
            else if (info.code <= Updater.installedCode(this)) msg = "최신 버전입니다 (" + Updater.installedName(this) + ")";
            else {
                runOnUiThread(() -> status.setText(info.name + " 받는 중…"));
                String err = Updater.downloadAndInstall(this, s, info);
                msg = err != null ? err : info.name + " 설치를 시작했습니다. 화면에 뜨는 '설치'를 눌러 주세요";
            }
            runOnUiThread(() -> {
                busy = false;
                status.setText(msg);
                resetIdle();
            });
        }).start();
    }

    private void open(Intent i) {
        try {
            startActivity(i);
        } catch (ActivityNotFoundException e) {
            // 일부 안드로이드 TV는 이 설정 화면이 없다. 그때는 PC에서 install-board-app.bat 으로 허용한다
            toast("이 TV에는 해당 설정 화면이 없습니다. PC에서 install-board-app.bat 을 실행하면 허용됩니다");
        }
    }

    private void toast(String m) {
        Toast.makeText(this, m, Toast.LENGTH_LONG).show();
    }

    private TextView text(LinearLayout l, String s, int sp) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setPadding(0, 12, 0, 4);
        l.addView(t);
        return t;
    }

    private EditText field(LinearLayout l, String label, String value, int inputType) {
        text(l, label, 18);
        EditText e = new EditText(this);
        e.setText(value);
        e.setInputType(inputType);
        e.setSingleLine();
        e.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        l.addView(e);
        return e;
    }

    private Button button(LinearLayout l, String label, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        b.setAllCaps(false);
        b.setOnClickListener(click);
        l.addView(b);
        return b;
    }
}
