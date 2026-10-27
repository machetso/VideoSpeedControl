import json, subprocess, sys, hashlib
P = sys.argv[1]
def packets(path):
    out = subprocess.run([P, "-v", "error", "-select_streams", "v:0", "-show_packets", "-show_data_hash", "sha256",
                          "-show_entries", "packet=pts_time,dts_time,duration_time,flags,data_hash:stream=time_base",
                          "-of", "json", path], capture_output=True, text=True).stdout
    return json.loads(out)["packets"]
def check(src, out, start=0, count=None):
    s, o = packets(src), packets(out)
    s_dec = s  # decode order
    hs = [p["data_hash"] for p in s]
    ho = [p["data_hash"] for p in o]
    # output packets must be the same bytes, same decode order, as a contiguous run of the source
    i = hs.index(ho[0])
    same = hs[i:i+len(ho)] == ho
    pts = sorted(float(p["pts_time"]) for p in o)
    d = [b - a for a, b in zip(pts, pts[1:])]
    print(f"{out}: {len(o)} packets, bit-identical={same} (from source packet {i}), "
          f"first pts {pts[0]:.6f}, last {pts[-1]:.6f}, frame step {min(d)*1e3:.3f}–{max(d)*1e3:.3f} ms")
    return pts
check("synth_hevc240.mp4", "hevc240_to25.mp4")
pts = check("synth_hevc240.mp4", "hevc240_sections.mp4")
# section borders: frame 240 at 1.0 s, 480 at 9.0 s, 600 at 11.0 s, end 12.5 s
for f in (240, 480, 600): print(f"  frame {f} at {pts[f]:.6f} s")
check("synth_avc120_rot.mp4", "avc120_trim.mp4")
