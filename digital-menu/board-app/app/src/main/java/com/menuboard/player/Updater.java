package com.menuboard.player;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * 최소 업데이트 수단: 매장 서버(POS기)의 /updates/board-app.json 을 보고 새 버전 APK를 받아 설치한다.
 * 보드는 인터넷이 아니라 매장 서버에서만 받는다. 매장 서버가 POSWING 업데이트 서버에서 정품 인증 토큰으로
 * 받아 pb_public/updates/ 에 놓아 두는 것은 서버 쪽 일이다.
 *
 * board-app.json 예: {"versionCode":2,"versionName":"1.1","apk":"menuboard-player-2.apk","sha256":"…64자…"}
 * build.sh 가 APK와 함께 만들어 준다.
 */
final class Updater {
    static final class Info {
        final int code;
        final String name, apk, sha256;

        Info(int code, String name, String apk, String sha256) {
            this.code = code;
            this.name = name;
            this.apk = apk;
            this.sha256 = sha256;
        }
    }

    private Updater() {}

    static long installedCode(Context c) {
        try {
            return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).getLongVersionCode();
        } catch (PackageManager.NameNotFoundException e) {
            return 0;
        }
    }

    static String installedName(Context c) {
        try {
            return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException e) {
            return "?";
        }
    }

    /** 서버에 올라온 버전 정보. 없거나 형식이 틀리면 null. 결과는 설정 화면에서 보이게 prefs에도 적는다. */
    static Info check(Context c, String server) {
        String body = Net.get("http://" + server + "/updates/board-app.json", 5000);
        Info info = null;
        if (body != null) {
            try {
                JSONObject j = new JSONObject(body);
                String apk = j.getString("apk");
                String sha = j.getString("sha256").toLowerCase();
                // 주소 조작을 막으려고 파일 이름만 받는다
                if (apk.matches("[A-Za-z0-9._-]+\\.apk") && sha.matches("[0-9a-f]{64}"))
                    info = new Info(j.getInt("versionCode"), j.optString("versionName", ""), apk, sha);
            } catch (Exception ignored) {
                // 형식이 틀린 파일은 없는 것으로 본다
            }
        }
        SharedPreferences.Editor e = c.getSharedPreferences("board", Context.MODE_PRIVATE).edit();
        if (info != null && info.code > installedCode(c)) e.putString("updateName", info.name + " (" + info.code + ")");
        else e.remove("updateName");
        e.apply();
        return info;
    }

    /** APK를 받아 sha256을 맞춰 본 뒤 설치를 시작한다. 실패하면 이유를, 설치를 시작했으면 null을 돌려준다. */
    static String downloadAndInstall(Context c, String server, Info info) {
        if (info.code <= installedCode(c)) return "이미 최신 버전입니다";
        if (!c.getPackageManager().canRequestPackageInstalls())
            return "설치 권한이 없습니다. '앱 설치 허용'을 먼저 켜 주세요";
        File apk = new File(c.getCacheDir(), "update.apk");
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            HttpURLConnection conn = (HttpURLConnection) new URL("http://" + server + "/updates/" + info.apk).openConnection();
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(30000);
            try {
                if (conn.getResponseCode() != 200) return "APK를 받지 못했습니다 (HTTP " + conn.getResponseCode() + ")";
                try (InputStream in = conn.getInputStream(); OutputStream out = new FileOutputStream(apk)) {
                    byte[] buf = new byte[64 * 1024];
                    for (int n; (n = in.read(buf)) > 0; ) {
                        md.update(buf, 0, n);
                        out.write(buf, 0, n);
                    }
                }
            } finally {
                conn.disconnect();
            }
            if (!hex(md.digest()).equals(info.sha256)) {
                apk.delete();
                return "받은 APK가 손상됐습니다(sha256 불일치). 설치하지 않았습니다";
            }
            install(c, apk);
            return null;
        } catch (Exception e) {
            apk.delete();
            return "업데이트 실패: " + e.getMessage();
        }
    }

    /**
     * 설치는 안드로이드가 한다. 서명이 지금 앱과 다르거나 버전이 낮으면 안드로이드가 거부하고 지금 앱이 그대로 남는다.
     * 일반 앱이라 리모컨으로 '설치'를 한 번 눌러야 한다(InstallReceiver 가 확인 화면을 띄운다).
     */
    // ponytail: 확인 없이 설치하려면 기기 소유자(device owner) 등록이나 보드 제조사 시스템 서명이 필요하다. 매장이 늘면 그때 붙인다.
    private static void install(Context c, File apk) throws Exception {
        PackageInstaller pi = c.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams p = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        p.setAppPackageName(c.getPackageName());
        p.setSize(apk.length());
        int id = pi.createSession(p);
        try (PackageInstaller.Session s = pi.openSession(id)) {
            try (InputStream in = new FileInputStream(apk); OutputStream out = s.openWrite("base.apk", 0, apk.length())) {
                byte[] buf = new byte[64 * 1024];
                for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                s.fsync(out);
            }
            PendingIntent done = PendingIntent.getBroadcast(c, id, new Intent(c, InstallReceiver.class),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
            s.commit(done.getIntentSender());
        }
    }

    private static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }
}
