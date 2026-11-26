package com.menuboard.player;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.provider.Settings;
import android.util.Log;

/**
 * 부팅이 끝났을 때와 새 버전으로 바뀌었을 때 메뉴판 화면을 다시 띄운다.
 * 안드로이드 10+ 는 '다른 앱 위에 표시'가 허용된 앱만 이렇게 화면을 띄울 수 있다(install-board-app.bat 이 허용해 둔다).
 * 홈 앱으로 지정된 보드에서는 이 수신기가 없어도 부팅 때 뜬다.
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        if (!Settings.canDrawOverlays(c)) {
            Log.w("MenuBoard", "다른 앱 위에 표시 권한이 없어 자동 실행을 못 합니다: " + i.getAction());
            return;
        }
        c.startActivity(new Intent(c, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
}
