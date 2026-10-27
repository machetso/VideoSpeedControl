#!/usr/bin/env bash
# Runs the on-device tests on the connected phone without uninstalling the app afterwards
# (Gradle's connectedAndroidTest uninstalls, which also deletes the pushed test clips).
#   tools/device_test.sh [CLIP.mp4 ...]   – clips are pushed to /data/local/tmp/vsc first
set -euo pipefail
cd "$(dirname "$0")/.."
export JAVA_HOME="${JAVA_HOME:-$HOME/Android/jdk}"
ADB="${ADB:-$HOME/Android/Sdk/platform-tools/adb}"
PKG=com.alexvulcu.videospeedcontrol
DIR=/data/local/tmp/vsc

./gradlew -q installDebug installDebugAndroidTest
"$ADB" shell mkdir -p "$DIR"
for clip in "$@"; do
    "$ADB" push "$clip" "$DIR/" >/dev/null
done
"$ADB" shell am instrument -w -r "$PKG.test/androidx.test.runner.AndroidJUnitRunner" \
    | grep -E "INSTRUMENTATION_STATUS: (class|test|stack)=|INSTRUMENTATION_STATUS_CODE: -[1-9]|^OK|^FAILURES|Tests run|INSTRUMENTATION_FAILED" \
    | sed -E 's/INSTRUMENTATION_STATUS: //'
