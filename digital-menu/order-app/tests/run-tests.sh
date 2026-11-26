#!/bin/sh
# 리눅스·맥에서 mono로 키패드 규칙 검사와 C# 5 빌드 확인을 한다. MONO_BIN에 mono의 bin 폴더(csc, mono)를 둔다.
set -e
cd "$(dirname "$0")/.."
BIN="${MONO_BIN:-}"; [ -n "$BIN" ] && BIN="$BIN/"
OUT="${TMPDIR:-/tmp}/menuboard-keypad-test"
mkdir -p "$OUT"
"${BIN}csc" -nologo -langversion:5 -target:winexe -out:"$OUT/MenuBoardKeypad.exe" \
  -r:System.Windows.Forms.dll -r:System.Drawing.dll -r:System.Web.Extensions.dll -r:System.Security.dll src/*.cs
"${BIN}csc" -nologo -langversion:5 -target:exe -out:"$OUT/KeypadLogicTests.exe" src/KeypadLogic.cs tests/KeypadLogicTests.cs
"${BIN}mono" "$OUT/KeypadLogicTests.exe"
