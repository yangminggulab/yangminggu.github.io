"""Post-process the final search index to add pinyin fields for pinyin-initial search.

Runs after render_search_previews.py and only touches public/search-index.previews.json,
so it is independent of the SyncTeX/enrich step and can be run locally. Pinyin is generated
only for title-like fields (block title, section, subsection) — full-text pinyin is huge
and its initials are so dense that almost any letter sequence would match, whereas
titles/terms are where pinyin-initial search ("xxds" → "线性代数") is actually useful.
"""

import json
from pathlib import Path

from pypinyin import lazy_pinyin, Style

BASE_DIR = Path(__file__).resolve().parent.parent
PREVIEWS_PATH = BASE_DIR / "public" / "search-index.previews.json"

TITLE_FIELDS = ("previewTitle", "blockTitle", "section", "subsection")


def _keep_non_han(chars):
    # errors callback: pass non-Han runs (latin/digits) through as individual characters
    # so "SVD分解" → "svd" + "fj", not a dropped prefix.
    return [c for c in chars]


def pinyin_initials(text):
    if not text:
        return ""
    return "".join(lazy_pinyin(text, style=Style.FIRST_LETTER, errors=_keep_non_han)).lower()


def pinyin_full(text):
    if not text:
        return ""
    return "".join(lazy_pinyin(text, errors=_keep_non_han)).lower()


def _has_han(text):
    return any("一" <= c <= "鿿" for c in text)


def title_source(block):
    seen = []
    for field in TITLE_FIELDS:
        value = (block.get(field) or "").strip()
        # Only Chinese-bearing titles are worth a pinyin index. English kind labels like
        # "Definition"/"Theorem" (assigned when a block has no real title yet) are skipped
        # so they don't pollute pinyinInitials with "definition" etc.
        if value and value not in seen and _has_han(value):
            seen.append(value)
    return " ".join(seen)


def main():
    if not PREVIEWS_PATH.exists():
        raise FileNotFoundError(f"Missing {PREVIEWS_PATH}")

    blocks = json.loads(PREVIEWS_PATH.read_text(encoding="utf-8"))
    with_pinyin = 0
    for block in blocks:
        src = title_source(block)
        initials = pinyin_initials(src)
        full = pinyin_full(src)
        block["pinyinInitials"] = initials
        block["pinyinFull"] = full
        if initials:
            with_pinyin += 1

    PREVIEWS_PATH.write_text(
        json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Added pinyin to {with_pinyin}/{len(blocks)} blocks -> {PREVIEWS_PATH}")


if __name__ == "__main__":
    main()
