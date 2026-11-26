package com.menuboard.player;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Process;

/**
 * 메뉴판 앱 다시 켜기. 별도 프로세스(:restart)에서 떠서 원래 프로세스를 끝내고 메뉴판을 새로 띄운 뒤 스스로 끝난다.
 * 한 프로세스 안에서 자기 자신을 죽이고 다시 띄우는 것보다 확실하다.
 */
// ponytail: 보드 전체 재부팅은 보드 제조사 시스템 서명(REBOOT 권한)이 있어야 한다. 1차는 앱 다시 켜기만.
public class RestartActivity extends Activity {
    static final String EXTRA_PID = "pid";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        int pid = getIntent().getIntExtra(EXTRA_PID, -1);
        if (pid > 0) Process.killProcess(pid);
        startActivity(new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK));
        finish();
        Runtime.getRuntime().exit(0);
    }
}
