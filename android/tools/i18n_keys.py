#!/usr/bin/env python3
"""Interface texts of the Android app: every English text in the code (tr("…") / trp(one, other, …))
and what each dictionary i18n/<code>.json still lacks.

    python3 android/tools/i18n_keys.py            # report
    python3 android/tools/i18n_keys.py --list     # the English texts, one per line (for translators)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "android/app/src/main/java"
I18N = ROOT / "i18n"
LIT = r'"((?:[^"\\]|\\.)*)"'
# texts that reach tr() through a variable (segmented button labels, enum labels)
EXTRA = ["Easy", "Pro", "Lossless", "Smart", "Re-encode",
         "AV1 (fast)", "AV1 (best quality, slow)", "HEVC (H.265)", "H.264", "Good", "High", "Very high"]


def _string(s: str, i: int) -> tuple[str | None, int]:
    """A string literal (possibly "a" + "b" + …) starting at s[i]; returns (text, end)."""
    parts = []
    while True:
        m = re.match(r'\s*' + LIT, s[i:])
        if not m:
            break
        parts.append(m.group(1))
        i += m.end()
        p = re.match(r'\s*\+\s*(?=")', s[i:])
        if not p:
            break
        i += p.end()
    return ("".join(parts).replace('\\"', '"') if parts else None), i


def keys() -> list[str]:
    out = []
    for f in sorted(SRC.rglob("*.kt")):
        s = f.read_text(encoding="utf-8")
        for m in re.finditer(r'\btr\(\s*', s):
            t, _ = _string(s, m.end())
            if t:
                out.append(t)
        for m in re.finditer(r'\btrp\(\s*', s):                 # the "other" form is the key
            one, i = _string(s, m.end())
            c = re.match(r'\s*,\s*', s[i:])
            if one and c:
                other, _ = _string(s, i + c.end())
                if other:
                    out.append(other)
        for name in ("EASY_INFO", "PRO_INFO"):
            m = re.search(name + r'\s*=\s*', s)
            if m:
                t, _ = _string(s, m.end())
                if t:
                    out.append(t)
    out += EXTRA
    return list(dict.fromkeys(out))


def main() -> None:
    k = keys()
    if "--list" in sys.argv:
        print("\n".join(k))
        return
    ph = re.compile(r'%[0-9.]*[sdf%]')
    print(f"{len(k)} texts in the code")
    for f in sorted(I18N.glob("*.json")):
        texts = json.loads(f.read_text(encoding="utf-8"))["texts"]
        missing = [x for x in k if x not in texts]
        bad = [x for x, v in texts.items() if any(ph.findall(x) != ph.findall(y)
               for y in (v.values() if isinstance(v, dict) else [v]))]
        print(f"{f.name}: {len(texts)} texts, {len(missing)} missing, {len(bad)} with other placeholders")
        for x in missing[:20]:
            print("   missing:", x)
        for x in bad[:20]:
            print("   placeholders:", x)


if __name__ == "__main__":
    main()
