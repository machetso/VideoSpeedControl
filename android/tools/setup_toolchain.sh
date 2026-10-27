#!/usr/bin/env bash
# VideoSpeedControl Android – installs the build toolchain into the user's home (no root):
#   JDK 21 (Temurin)  → ~/Android/jdk
#   Android SDK       → ~/Android/Sdk  (cmdline-tools, platform-tools, platform, build-tools, NDK)
# Re-running is safe; finished parts are skipped. Prints the env lines for ~/.bashrc at the end.
set -euo pipefail

ROOT="${VSC_ANDROID_ROOT:-$HOME/Android}"
JDK_DIR="$ROOT/jdk"
SDK_DIR="$ROOT/Sdk"
CMDLINE_ZIP="commandlinetools-linux-15859902_latest.zip"
PLATFORM="android-37.2"
BUILD_TOOLS="37.0.0"

mkdir -p "$ROOT" "$SDK_DIR"
tmp="$(mktemp -d /tmp/opencode/vsc-toolchain.XXXX 2>/dev/null || mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if [ ! -x "$JDK_DIR/bin/java" ]; then
    echo "== JDK 21"
    curl -fL --retry 3 -o "$tmp/jdk.tar.gz" \
        "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse"
    mkdir -p "$JDK_DIR"
    tar -xzf "$tmp/jdk.tar.gz" -C "$JDK_DIR" --strip-components=1
fi
export JAVA_HOME="$JDK_DIR"
export PATH="$JAVA_HOME/bin:$PATH"

if [ ! -x "$SDK_DIR/cmdline-tools/latest/bin/sdkmanager" ]; then
    echo "== Android command-line tools"
    curl -fL --retry 3 -o "$tmp/cmdline.zip" "https://dl.google.com/android/repository/$CMDLINE_ZIP"
    unzip -q "$tmp/cmdline.zip" -d "$tmp"
    mkdir -p "$SDK_DIR/cmdline-tools"
    rm -rf "$SDK_DIR/cmdline-tools/latest"
    mv "$tmp/cmdline-tools" "$SDK_DIR/cmdline-tools/latest"
fi
SDKM="$SDK_DIR/cmdline-tools/latest/bin/sdkmanager"

echo "== Licences"
yes | "$SDKM" --sdk_root="$SDK_DIR" --licenses >/dev/null || true

# Newest stable NDK (no -beta / -rc)
NDK="$("$SDKM" --sdk_root="$SDK_DIR" --list 2>/dev/null \
    | grep -oE 'ndk;[0-9]+\.[0-9]+\.[0-9]+ ' | sort -t';' -k2 -V | tail -1 | tr -d ' ')"
echo "== SDK packages: platform-tools, platforms;$PLATFORM, build-tools;$BUILD_TOOLS, $NDK"
"$SDKM" --sdk_root="$SDK_DIR" --install \
    "platform-tools" "platforms;$PLATFORM" "build-tools;$BUILD_TOOLS" "$NDK"

cat <<EOF

Done. Add to ~/.bashrc:
  export JAVA_HOME="$JDK_DIR"
  export ANDROID_HOME="$SDK_DIR"
  export ANDROID_NDK_HOME="$SDK_DIR/${NDK/;//}"
  export PATH="\$JAVA_HOME/bin:\$ANDROID_HOME/platform-tools:\$PATH"
EOF
