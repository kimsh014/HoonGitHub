package com.menuboard.player;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** 서버 주소·화면 번호·글자 배율 설정. 터치가 없어도 방향키·마우스로 이동할 수 있는 기본 위젯만 쓴다. */
public class SettingsActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        SharedPreferences prefs = getSharedPreferences("board", MODE_PRIVATE);
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(48, 32, 48, 32);

        EditText server = field(l, "서버 주소 (예: 192.168.0.10:8090)", prefs.getString("server", ""),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        EditText screen = field(l, "화면 번호 (1~4)", String.valueOf(prefs.getInt("screen", 1)),
                InputType.TYPE_CLASS_NUMBER);
        EditText zoom = field(l, "글자 크기 배율 (%)", String.valueOf(prefs.getInt("zoom", 100)),
                InputType.TYPE_CLASS_NUMBER);

        Button save = new Button(this);
        save.setText("저장");
        save.setOnClickListener(v -> {
            String err = MainActivity.save(prefs, server.getText().toString(),
                    screen.getText().toString(), zoom.getText().toString());
            if (err != null) Toast.makeText(this, err, Toast.LENGTH_LONG).show();
            else finish();
        });
        l.addView(save);

        // 이 앱이 홈 앱이라 와이파이 설정 등으로 나갈 길이 필요하다
        Button system = new Button(this);
        system.setText("안드로이드 설정 열기");
        system.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_SETTINGS)));
        l.addView(system);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(l);
        setContentView(scroll);
    }

    private EditText field(LinearLayout l, String label, String value, int inputType) {
        TextView t = new TextView(this);
        t.setText(label);
        l.addView(t);
        EditText e = new EditText(this);
        e.setText(value);
        e.setInputType(inputType);
        e.setSingleLine();
        l.addView(e);
        return e;
    }
}
