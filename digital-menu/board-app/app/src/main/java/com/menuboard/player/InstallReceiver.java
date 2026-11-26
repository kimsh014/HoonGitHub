package com.menuboard.player;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.util.Log;
import android.widget.Toast;

/** 업데이트 설치 결과. 사용자 확인이 필요하면 안드로이드의 설치 확인 화면을 띄운다. */
public class InstallReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        int status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = i.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) c.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            return;
        }
        if (status == PackageInstaller.STATUS_SUCCESS) return; // 새 앱이 MY_PACKAGE_REPLACED 로 스스로 다시 뜬다
        String msg = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        Log.w("MenuBoard", "업데이트 설치 실패(" + status + "): " + msg);
        Toast.makeText(c, "업데이트 설치 실패: " + msg + "\n지금 버전으로 계속 동작합니다", Toast.LENGTH_LONG).show();
    }
}
