# Helpers for driving the app on the phone from a shell (source this file):
#   dump – UI hierarchy XML; tapText TEXT [tail] – tap the first (last) view with this text;
#   bounds TEXT – its bounds "x1 y1 x2 y2"; scrollDown [N] – swipe up N times.
A=${ADB:-$HOME/Android/Sdk/platform-tools/adb}
dump() { $A shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; $A shell cat /sdcard/ui.xml; }
bounds() { dump | grep -oE "text=\"$1\"[^>]*bounds=\"[^\"]+\"" | ${2:-head} -1 | grep -oE '\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]' | tr '[],' '   '; }
tapText() { B=$(bounds "$1" "$2"); [ -z "$B" ] && { echo "not found: $1"; return 1; }; read x1 y1 x2 y2 <<< $B; $A shell input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 )); }
scrollDown() { for i in $(seq 1 ${1:-3}); do $A shell input swipe 540 2000 540 500 300; sleep 0.3; done; }
