package com.menuboard.player;

import android.content.Context;
import android.os.Environment;
import android.os.storage.StorageManager;
import android.os.storage.StorageVolume;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 현장 비상용: USB 메모리 맨 위 폴더의 menuboard.txt 를 읽어 설정을 바꾼다. 서버에 못 붙어 원격 관리가 안 될 때 쓴다.
 * 같은 내용은 한 번만 적용한다(USB를 꽂아 둔 채 재부팅해도 다시 적용하지 않음).
 *
 * 파일 예 (메모장으로 만들고 UTF-8로 저장, # 뒤는 설명):
 *   server=192.168.0.10:8090
 *   screen=2
 *   zoom=120
 *   rotation=90       (0, 90, 180, 270)
 *   brightness=80     (10~100, -1 = 기본)
 *   as=60             (A/S 연결(네트워크 ADB)을 60분 열기, 0 = 바로 잠금)
 *   restart=yes       (적용 뒤 앱 다시 켜기)
 *
 * 안드로이드 11+ 에서 다른 앱이 만든 파일을 읽으려면 '모든 파일 접근' 권한이 있어야 한다(설치 bat이 허용).
 */
final class UsbConfig {
    static final String FILE = "menuboard.txt";

    private UsbConfig() {}

    /** 꽂힌 USB에서 menuboard.txt 를 찾는다. 없으면 null. */
    static File find(Context c) {
        StorageManager sm = c.getSystemService(StorageManager.class);
        if (sm == null) return null;
        for (StorageVolume v : sm.getStorageVolumes()) {
            if (!v.isRemovable() || !Environment.MEDIA_MOUNTED.equals(v.getState())) continue;
            File dir = v.getDirectory();
            if (dir == null) continue;
            File f = new File(dir, FILE);
            if (f.isFile()) return f;
        }
        return null;
    }

    static boolean canRead() {
        return Environment.isExternalStorageManager();
    }

    /** key=value 줄을 읽는다. 키는 소문자로, # 뒤와 앞뒤 공백은 버린다. 32KB 넘는 파일은 읽지 않는다. */
    static Map<String, String> read(File f) throws Exception {
        if (f.length() > 32 * 1024) throw new IllegalArgumentException("파일이 너무 큽니다");
        String text = new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8);
        if (text.startsWith("﻿")) text = text.substring(1); // 메모장이 붙이는 BOM
        Map<String, String> m = new LinkedHashMap<>();
        for (String line : text.split("\r?\n")) {
            int hash = line.indexOf('#');
            if (hash >= 0) line = line.substring(0, hash);
            int eq = line.indexOf('=');
            if (eq <= 0) continue;
            m.put(line.substring(0, eq).trim().toLowerCase(), line.substring(eq + 1).trim());
        }
        return m;
    }
}
