import subprocess, sys, array
FF = sys.argv[1]
def pcm(path):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    return array.array("h", raw)
def freq(s, a, b):
    seg = s[a:b]
    z = sum(1 for x, y in zip(seg, seg[1:]) if (x < 0) != (y < 0))
    return z / 2 / ((b - a) / 48000)
for name in sys.argv[2:]:
    s = pcm(name)
    dur = len(s) / 48000
    w = 24000
    fs = [freq(s, i, i + w) for i in range(0, len(s) - w + 1, w)]
    print(f"{name}: {dur:.3f} s, pitch per 0.5 s: min {min(fs):.0f} Hz, max {max(fs):.0f} Hz")
    if "sections" in name:
        print("   ", " ".join(f"{f:.0f}" for f in fs))
