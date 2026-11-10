"""Shipped UI sources must be English. CJK is allowlisted only for legacy
None-option detection / relabel and for non-UI LLM judge prompts.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.harness import ROOT

CJK_RE = re.compile(r"[\u3400-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]")
LEGACY_NONE = "\u4ee5\u4e0a\u7686\u975e"
SHIPPED_SUFFIXES = {".js", ".py"}
SKIP_DIRS = {".git", "tests", "examples", "docs", "__pycache__", "node_modules"}

# theme_engine.py judge prompts are sent to the model, not shown as node UI.
THEME_ENGINE_PROMPTS = (
    "\u63d0\u793a\u8a5e\u660e\u78ba\u9700\u8981\u6216\u5f37\u70c8\u6697\u793a\u6b64\u9078\u9805",
    "\u63d0\u793a\u8a5e\u4e0d\u9700\u8981\u6b64\u9078\u9805",
    "\u5177\u9ad4\u9078\u9805\uff1a",
    "\u662f\u5426\u61c9\u555f\u7528\u6b64\u9078\u9805\uff1f",
)

LEGACY_MARKERS = (
    "LEGACY_DEFAULT_NONE",
    "NONE_LIKE",
    "isLegacyDefaultNone",
    "is_legacy_default_none",
    "relabel_legacy_default_none",
    "relabelLegacyDefaultNone",
    "auto-generated default",
    "Former auto-generated",
    "former auto-generated",
)


def _shipped_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SHIPPED_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _line_allowed(path: Path, line: str) -> bool:
    if not CJK_RE.search(line):
        return True
    remainder = line
    if path.name == "theme_engine.py":
        for token in THEME_ENGINE_PROMPTS:
            remainder = remainder.replace(token, "")
        return not CJK_RE.search(remainder)
    if LEGACY_NONE in line and any(marker in line for marker in LEGACY_MARKERS):
        remainder = line.replace(LEGACY_NONE, "")
        return not CJK_RE.search(remainder)
    return False


class EnglishUiSourceTests(unittest.TestCase):
    def test_shipped_ui_sources_have_no_unexpected_cjk(self):
        violations = []
        for path in _shipped_files():
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                if CJK_RE.search(line) and not _line_allowed(path, line):
                    rel = path.relative_to(ROOT)
                    violations.append(f"{rel}:{number}:{line.strip()}")
        self.assertEqual(violations, [], "unexpected CJK in shipped UI sources:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
