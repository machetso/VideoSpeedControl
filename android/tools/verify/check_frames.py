import subprocess, sys
from fractions import Fraction as F
FF = sys.argv[1]
W, H = 160, 90
def gray(path, vf=""):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-vf", (vf + "," if vf else "") + f"scale={W}:{H}:flags=area,format=gray",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (W * H)
    return [raw[i * W * H:(i + 1) * W * H] for i in range(n)]
def mse(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
def pieces(segs, start, end, base):
    runs, pos = [], start
    for a, b, r in segs:
        if a > pos: runs.append((pos, a, base))
        runs.append((a, b, r)); pos = b
    if pos < end: runs.append((pos, end, base))
    out, t = [], F(0)
    for a, b, r in runs:
        out.append((a, b, r, t)); t += F(b - a) / r
    return out
def shown(ps, t):
    """last source frame that has started by output time t"""
    for a, b, r, t0 in ps:
        if t < t0 + F(b - a) / r:
            return a + int((t - t0) * r)
    return ps[-1][1] - 1
def check(name, src, out, ps, fps, crop=""):
    s, o = gray(src, crop), gray(out)
    bad, worst = 0, 0
    for k, img in enumerate(o):
        f = shown(ps, F(k, 1) / fps)
        cands = {g: mse(img, s[g]) for g in (f - 1, f, f + 1) if 0 <= g < len(s)}
        best = min(cands, key=cands.get)
        if best != f and cands[best] < cands[f] * 0.9: bad += 1
        worst = max(worst, cands[f])
    print(f"{name}: {len(o)} output frames, {bad} not showing the expected source frame, worst MSE {worst:.1f}")
check("sections 240→60 fps", "synth_hevc240.mp4", "re_sections60.mp4",
      pieces([(240, 480, F(30))], 0, 960, F(240)), F(60))
check("trim 101–251, every frame once at 30", "synth_hevc240.mp4", "re_trim30.mp4",
      pieces([], 101, 251, F(30)), F(30))

s, o = gray("synth_hevc240.mp4"), gray("re_trim30.mp4")
vals = sorted(mse(o[k], s[101 + k]) for k in range(len(o)))
print("trim: MSE median %.1f, 90%% %.1f, max %.1f" % (vals[len(vals)//2], vals[int(len(vals)*.9)], vals[-1]))
ks = sorted(range(len(o)), key=lambda k: -mse(o[k], s[101 + k]))[:3]
print("worst frames (output index):", ks, " neighbour MSE for worst:", [round(mse(o[ks[0]], s[101 + ks[0] + d]),1) for d in (-1,0,1)])
