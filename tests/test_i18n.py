# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Desktop interface languages: formatting, plurals and every dictionary's placeholders."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from vsc import i18n

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import i18n_desktop  # noqa: E402

PH = re.compile(r"%(\d+\$)?[-+0#,]*\d*(?:\.\d+)?([sdfigeExX])")


def placeholders(text):
    """Placeholder types in the order the values are used: plain ones in reading order,
    positional ones (%2$s) by their number – a translation may reorder only with positions."""
    found = PH.findall(text.replace("%%", ""))
    if any(pos for pos, _ in found):
        return [c for _, c in sorted(((int(pos[:-1]) if pos else i + 1), c) for i, (pos, c) in enumerate(found))]
    return [c for _, c in found]


@pytest.fixture(autouse=True)
def english_again():
    yield
    i18n.use("en")


def test_format_and_plural():
    i18n.use("en")
    assert i18n.tr("%s of %d at %.1f fps", "a", 3, 2.25) == "a of 3 at 2.2 fps"
    assert i18n.tr("%1$s / %2$s", "x", "y") == "x / y"
    assert i18n.trp("%d clip", "%d clips", 1, 1) == "1 clip"
    assert i18n.trp("%d clip", "%d clips", 4, 4) == "4 clips"
    assert i18n.plural_category("ro", 15) == "few" and i18n.plural_category("he", 2) == "two"


def test_german_dictionary_is_used():
    i18n.use("de")
    assert i18n.current().code == "de"
    i18n.use("xx")                      # unknown → the computer's language or English
    assert i18n.current().code in {l.code for l in i18n.languages()}


@pytest.mark.parametrize("code", sorted(p.stem for p in (ROOT / "i18n").glob("*.json")))
def test_dictionary_placeholders_match(code):
    d = json.loads((ROOT / "i18n" / f"{code}.json").read_text(encoding="utf-8"))
    bad = []
    for key, value in d["texts"].items():
        forms = value.values() if isinstance(value, dict) else [value]
        for v in forms:
            if not isinstance(v, str) or (v.strip() == "" and key.strip() != ""):
                bad.append((key, v))
            elif placeholders(v) != placeholders(key):
                bad.append((key, v))          # every form keeps every placeholder (dropping the first one shifts the values)
    assert not bad, f"{code}: {len(bad)} texts with wrong placeholders, e.g. {bad[:3]}"


def test_every_desktop_text_is_translated():
    keys = i18n_desktop.keys()
    missing = {code: [t for t in keys if t not in d["texts"]]
               for code, d in i18n_desktop.dictionaries().items()}
    assert not any(missing.values()), {c: len(m) for c, m in missing.items() if m}
