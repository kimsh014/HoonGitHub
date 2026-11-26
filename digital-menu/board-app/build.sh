#!/usr/bin/env bash
# Gradle 없이 안드로이드 SDK 도구만으로 APK를 만든다 (Git Bash용).
# 결과: build/menuboard-player.apk
# ponytail: 디버그 키로만 서명한다. 출시용은 별도 키스토어로 apksigner 단계만 바꾸면 된다.
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_SDK:-$(cygpath -m "$LOCALAPPDATA")/Android/Sdk}"
BT="$SDK/build-tools/36.0.0"
JAR="$SDK/platforms/android-37.0/android.jar"
JDK="${JDK_HOME:-C:/Program Files/Android/Android Studio/jbr}"
JAVA="$JDK/bin/java"
SRC=app/src/main
OUT=build

rm -rf "$OUT" && mkdir -p "$OUT/classes" "$OUT/dex"

# 디버그 서명 키 (표준 디버그 값)
if [ ! -f .debug.keystore ]; then
  "$JDK/bin/keytool" -genkeypair -keystore .debug.keystore -storepass android \
    -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Android Debug,O=Android,C=US"
fi

# 1. 리소스 컴파일·링크
"$BT/aapt2" compile --dir "$SRC/res" -o "$OUT/res.zip"
"$BT/aapt2" link -o "$OUT/unsigned.apk" -I "$JAR" --manifest "$SRC/AndroidManifest.xml" \
  --min-sdk-version 30 --target-sdk-version 34 --version-code 1 --version-name 1.0 "$OUT/res.zip"

# 2. 자바 컴파일 → dex
"$JDK/bin/javac" --release 17 -encoding UTF-8 -Xlint:-options -cp "$JAR" -d "$OUT/classes" \
  $(find "$SRC/java" -name '*.java')
"$JAVA" -cp "$BT/lib/d8.jar" com.android.tools.r8.D8 --release --min-api 30 --lib "$JAR" \
  --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')

# 3. APK에 classes.dex 넣기 → 정렬 → 서명
"$JDK/bin/jar" --update --no-manifest --file "$OUT/unsigned.apk" -C "$OUT/dex" classes.dex
"$BT/zipalign" -p -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$JAVA" -jar "$BT/lib/apksigner.jar" sign --ks .debug.keystore --ks-pass pass:android \
  --key-pass pass:android --out "$OUT/menuboard-player.apk" "$OUT/aligned.apk"
"$JAVA" -jar "$BT/lib/apksigner.jar" verify "$OUT/menuboard-player.apk"
echo "완료: $(pwd)/$OUT/menuboard-player.apk"
