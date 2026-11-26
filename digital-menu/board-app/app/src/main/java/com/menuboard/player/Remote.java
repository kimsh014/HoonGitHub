package com.menuboard.player;

import android.Manifest;
import android.content.ContentResolver;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

/**
 * TV 원격 관리의 TV 쪽 통신. 매장 서버(pb_hooks/devices.pb.js)에 등록하고, 15초마다 지금 설정을 보고하며
 * 할 일(설정 바꾸기·재시작·캡처·A/S 연결)을 받는다. 모두 백그라운드 스레드에서 부른다.
 */
final class Remote {
    private static final String TAG = "MenuBoard";

    private Remote() {}

    /** 서버가 돌려준 할 일. */
    static final class Orders {
        int rev, restartRev, shotRev;
        long adbSeconds;
        JSONObject desired;
    }

    /** 보고하고 할 일을 받는다. 토큰이 없거나 서버가 TV를 모르면(지워짐) 새로 등록한다. 실패하면 null. */
    static Orders report(Context c, String server, JSONObject reported) {
        SharedPreferences p = c.getSharedPreferences("board", Context.MODE_PRIVATE);
        String token = p.getString("deviceToken", null);
        String tokenServer = p.getString("deviceServer", null);
        if (token == null || !server.equals(tokenServer)) {
            token = register(c, server);
            if (token == null) return null;
        }
        try {
            JSONObject body = new JSONObject()
                    .put("version", Updater.installedName(c))
                    .put("model", model())
                    .put("reported", reported);
            Net.Reply r = Net.post("http://" + server + "/api/menuboard/devices/report", token, "application/json",
                    body.toString().getBytes(StandardCharsets.UTF_8), 5000);
            if (r.status == 401) {
                // 관리 화면에서 지운 TV: 토큰을 버리고 다음 보고 때 새로 등록한다
                p.edit().remove("deviceToken").apply();
                return null;
            }
            if (r.status != 200) return null;
            JSONObject j = new JSONObject(r.body);
            Orders o = new Orders();
            o.rev = j.optInt("rev");
            o.restartRev = j.optInt("restartRev");
            o.shotRev = j.optInt("shotRev");
            o.adbSeconds = j.optLong("adbSeconds");
            o.desired = j.optJSONObject("desired");
            if (o.desired == null) o.desired = new JSONObject();
            return o;
        } catch (Exception e) {
            Log.w(TAG, "보고 실패", e);
            return null;
        }
    }

    // ponytail: 서버에 매장이 여럿이면(프랜차이즈 서버) 매장 번호를 함께 보내야 한다. 지금은 매장 하나인 서버만.
    private static String register(Context c, String server) {
        try {
            JSONObject body = new JSONObject().put("model", model()).put("version", Updater.installedName(c));
            Net.Reply r = Net.post("http://" + server + "/api/menuboard/devices/register", null, "application/json",
                    body.toString().getBytes(StandardCharsets.UTF_8), 5000);
            if (r.status != 200) return null;
            String token = new JSONObject(r.body).getString("token");
            // 등록 전에 쌓인 재시작·캡처 요청은 따르지 않도록 기준 번호를 지운다(-1 = 다음 보고 값을 기준으로)
            c.getSharedPreferences("board", Context.MODE_PRIVATE).edit()
                    .putString("deviceToken", token).putString("deviceServer", server)
                    .putInt("appliedRev", 0).putInt("restartRev", -1).putInt("shotRev", -1).apply();
            Log.i(TAG, "매장 서버에 TV로 등록했습니다");
            return token;
        } catch (Exception e) {
            return null;
        }
    }

    /** 화면 캡처를 올린다. 가로 1280 이하로 줄여 JPEG로 보낸다. */
    static boolean uploadShot(Context c, String server, Bitmap shot) {
        String token = c.getSharedPreferences("board", Context.MODE_PRIVATE).getString("deviceToken", null);
        if (token == null) return false;
        Bitmap b = shot;
        if (shot.getWidth() > 1280) {
            b = Bitmap.createScaledBitmap(shot, 1280, Math.max(1, shot.getHeight() * 1280 / shot.getWidth()), true);
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        b.compress(Bitmap.CompressFormat.JPEG, 75, out);
        if (b != shot) b.recycle();
        Net.Reply r = Net.post("http://" + server + "/api/menuboard/devices/shot", token, "image/jpeg", out.toByteArray(), 15000);
        return r.status == 200;
    }

    static String model() {
        return (Build.MANUFACTURER + " " + Build.MODEL + " / Android " + Build.VERSION.RELEASE).trim();
    }

    // ── A/S 연결(네트워크 ADB) ──
    // 일반 앱은 ADB를 켜고 끌 수 없다. 설치 bat이 adb로 WRITE_SECURE_SETTINGS 권한을 주면 그때부터 이 앱이
    // 평소에는 ADB를 꺼 두고(잠금), 관리 화면이나 USB 설정 파일로 연 시간 동안만 켠다.
    // 네트워크로 붙는 포트(보통 5555)는 보드 펌웨어 설정(persist.adb.tcp.port)을 따른다.

    static boolean canAdb(Context c) {
        return c.checkSelfPermission(Manifest.permission.WRITE_SECURE_SETTINGS) == PackageManager.PERMISSION_GRANTED;
    }

    /** 지금 ADB가 켜져 있는지. 알 수 없으면 null. */
    static Boolean adbOn(Context c) {
        try {
            return Settings.Global.getInt(c.getContentResolver(), Settings.Global.ADB_ENABLED) == 1;
        } catch (Settings.SettingNotFoundException e) {
            return null;
        }
    }

    /** ADB를 켜거나 끈다. 권한이 없으면 아무것도 안 한다. */
    static void setAdb(Context c, boolean on) {
        if (!canAdb(c)) return;
        Boolean now = adbOn(c);
        if (now != null && now == on) return;
        ContentResolver cr = c.getContentResolver();
        try {
            Settings.Global.putInt(cr, Settings.Global.ADB_ENABLED, on ? 1 : 0);
            Settings.Global.putInt(cr, "adb_wifi_enabled", on ? 1 : 0); // 안드로이드 11+ 무선 디버깅
            Log.i(TAG, "A/S 연결(ADB) " + (on ? "열림" : "잠금"));
        } catch (SecurityException e) {
            Log.w(TAG, "ADB 설정 실패", e);
        }
    }
}
