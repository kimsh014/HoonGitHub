package com.menuboard.player;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/** 매장 서버와의 짧은 HTTP 요청, 그리고 같은 망에서 매장 서버 찾기. 모두 백그라운드 스레드에서 부른다. */
final class Net {
    static final int DEFAULT_PORT = 8090;

    private Net() {}

    /** 응답 코드. 연결이 안 되면 -1. */
    static int status(String url, int timeoutMs) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            try {
                return c.getResponseCode();
            } finally {
                c.disconnect();
            }
        } catch (Exception e) {
            return -1;
        }
    }

    /** 본문을 문자열로. 200이 아니면 null. */
    static String get(String url, int timeoutMs) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setUseCaches(false);
            try {
                if (c.getResponseCode() != 200) return null;
                try (InputStream in = c.getInputStream()) {
                    ByteArrayOutputStream out = new ByteArrayOutputStream();
                    byte[] buf = new byte[8192];
                    for (int n; (n = in.read(buf)) > 0; ) {
                        out.write(buf, 0, n);
                        if (out.size() > 256 * 1024) return null; // 설정 파일만 받는다
                    }
                    return out.toString("UTF-8");
                }
            } finally {
                c.disconnect();
            }
        } catch (Exception e) {
            return null;
        }
    }

    static boolean healthy(String server) {
        return status("http://" + server + "/api/health", 3000) == 200;
    }

    /**
     * 이 기기와 같은 망(앞 24비트가 같은 주소 254개)에서 8090 포트로 메뉴판 서버를 찾는다.
     * /api/menuboard/store 가 200이면 메뉴판 서버로 본다. 몇 초 걸린다.
     */
    static List<String> discover(Context ctx) {
        List<String> found = Collections.synchronizedList(new ArrayList<>());
        byte[] me = localIPv4(ctx);
        if (me == null) return found;
        ExecutorService pool = Executors.newFixedThreadPool(32);
        for (int i = 1; i < 255; i++) {
            if (i == (me[3] & 0xff)) continue;
            String host = (me[0] & 0xff) + "." + (me[1] & 0xff) + "." + (me[2] & 0xff) + "." + i + ":" + DEFAULT_PORT;
            pool.execute(() -> {
                if (status("http://" + host + "/api/menuboard/store", 800) == 200) found.add(host);
            });
        }
        pool.shutdown();
        try {
            pool.awaitTermination(30, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
        // ponytail: /24 망만 찾는다. 매장 망이 더 넓으면(예: 255.255.0.0) 서버 주소를 직접 적어야 한다.
        List<String> out = new ArrayList<>(found);
        Collections.sort(out);
        return out;
    }

    private static byte[] localIPv4(Context ctx) {
        ConnectivityManager cm = ctx.getSystemService(ConnectivityManager.class);
        Network n = cm == null ? null : cm.getActiveNetwork();
        LinkProperties lp = n == null ? null : cm.getLinkProperties(n);
        if (lp == null) return null;
        for (LinkAddress a : lp.getLinkAddresses()) {
            InetAddress ip = a.getAddress();
            if (ip instanceof Inet4Address && !ip.isLoopbackAddress()) return ip.getAddress();
        }
        return null;
    }
}
