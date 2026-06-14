import json
from collections import Counter
from pathlib import Path

import fitz

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "public" / "search-index.enriched.json"
OUTPUT_DIR = BASE_DIR / "public" / "search-previews"
OUTPUT_PATH = BASE_DIR / "public" / "search-index.previews.json"
CHANGED_FILE = BASE_DIR / "build_changed.json"

# Which LaTeX environments get a rendered preview image. Everything else falls back
# to a text snippet on the frontend.
FRAME_KINDS = {
    "definition", "theorem", "example", "note", "remark",
    "proposition", "lemma", "corollary", "dxtips",
}

# ── Clipping geometry ────────────────────────────────────────────────────────
# These notes render two visual shapes:
#   * "framed" blocks (definition/theorem/dxtips/lemma/proposition/corollary) are
#     tcolorbox cards with a vivid colored border — we clip the box exactly.
#   * "unframed" blocks (example/note/remark) are plain text opened by a colored
#     label ("解"/"笔记"/"注") — we clip from the label line down to the next block.
#
# The anchor is `pdfLocator` (the SyncTeX mapping of the block's \begin line, already
# computed by enrich-search-index.ts). Its `y` is a top-down PDF coordinate and is used
# directly — no flipping. The previous implementation flipped it and also relied on the
# \end-line mapping for the bottom edge, which routinely overshot to whole-page clips.
BOX_MIN_WIDTH = 300          # a frame card spans most of the text column
BOX_MIN_HEIGHT = 8
FRAME_MARGIN = 3.5           # tiny breathing room around a detected card
NOFRAME_TOP_PAD = 5          # include the full label line above the anchor baseline
NOFRAME_MAX_H = 240          # cap an unframed clip so long blocks stay thumbnail-sized
NEXT_BLOCK_GAP = 8           # stop just above the next block's anchor
NEXT_BOX_GAP = 6             # stop just above the next colored card
PAGE_BOTTOM_MARGIN = 36
TEXT_LEFT_FALLBACK = 66      # used when the locator lacks x/W
RENDER_SCALE = 2             # 2x pixmap for crisp thumbnails


def load_changed_set():
    # Route B incremental: repos absent from changed_repos reuse their existing preview
    # entries (and on-disk PNGs) instead of being re-rendered. Missing file → full render.
    if not CHANGED_FILE.exists():
        return set(), False
    try:
        data = json.loads(CHANGED_FILE.read_text(encoding="utf-8"))
        return set(data.get("changed_repos", [])), True
    except Exception:
        return set(), False


def resolve_best_pdf_path(block):
    debug_pdf_path = block.get("debugPdfPath")
    if debug_pdf_path and Path(debug_pdf_path).exists():
        return Path(debug_pdf_path)

    synctex = block.get("synctex")
    if synctex:
        main_pdf = Path(synctex).parent / "main.pdf"
        if main_pdf.exists():
            return main_pdf

    pdf_rel = block.get("pdf")
    if pdf_rel:
        copied_pdf = BASE_DIR / pdf_rel
        if copied_pdf.exists():
            return copied_pdf

    return None


def is_frame_border(fill):
    """A tcolorbox border is a vivid hue (large channel spread) that is not a pale
    background. Backgrounds have a high min channel; borders have a low one. The four
    themes seen across all PDFs (purple/orange/green/blue) all satisfy this."""
    if not fill:
        return False
    return (max(fill) - min(fill)) > 0.2 and min(fill) < 0.85


def detect_frame_boxes(page):
    """Colored frame-card rectangles on the page, sorted top-down."""
    boxes = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if (rect.width > BOX_MIN_WIDTH and rect.height > BOX_MIN_HEIGHT
                and is_frame_border(drawing.get("fill"))):
            boxes.append(fitz.Rect(rect))
    boxes.sort(key=lambda r: r.y0)
    return boxes


def get_text_lines(page):
    """Flat list of text lines as (y0, y1, x0, x1) bboxes, sorted top-down."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            lines.append((y0, y1, x0, x1))
    lines.sort()
    return lines


def frame_clip(box, page):
    m = FRAME_MARGIN
    return fitz.Rect(
        max(0, box.x0 - m),
        max(0, box.y0 - m),
        min(page.rect.width, box.x1 + m),
        min(page.rect.height, box.y1 + m),
    )


def noframe_clip(page, anchor_y, next_anchor_y, boxes):
    """Clip an unframed (label + plain text) block: from its label line down to the
    start of the next block (next colored card, next block anchor, height cap, or page
    bottom — whichever comes first)."""
    lines = get_text_lines(page)
    if not lines:
        return None

    # The label line is the text line whose center is closest to the anchor baseline.
    ai = min(range(len(lines)),
             key=lambda i: abs((lines[i][0] + lines[i][1]) / 2 - anchor_y))
    top = max(0, lines[ai][0] - NOFRAME_TOP_PAD)

    ph = page.rect.height
    bottom = min(ph - PAGE_BOTTOM_MARGIN, top + NOFRAME_MAX_H)
    if next_anchor_y is not None and next_anchor_y > anchor_y + 10:
        bottom = min(bottom, next_anchor_y - NEXT_BLOCK_GAP)
    for box in boxes:
        if box.y0 > anchor_y + 10:
            bottom = min(bottom, box.y0 - NEXT_BOX_GAP)
            break

    if bottom <= top:
        return None

    # Left/right hug the actual text in the clipped band. The locator's own x/W is the
    # label line's box and is unreliable (some labels report a negative width), so it is
    # not used for horizontal extent.
    band = [ln for ln in lines if ln[1] > top and ln[0] < bottom]
    if band:
        left = max(0, min(ln[2] for ln in band) - 4)
        right = min(page.rect.width, max(ln[3] for ln in band) + 4)
    else:
        left = TEXT_LEFT_FALLBACK
        right = page.rect.width - TEXT_LEFT_FALLBACK
    if right - left < 80:  # degenerate band → fall back to the text column
        left = TEXT_LEFT_FALLBACK
        right = page.rect.width - TEXT_LEFT_FALLBACK

    return fitz.Rect(left, top, right, bottom)


def compute_clip(page, locator, next_anchor_y):
    """Return (clip_rect, mode). mode is 'frame', 'noframe', or None with a reason."""
    anchor_y = locator.get("y")
    if anchor_y is None:
        return None, "locator missing y"

    boxes = detect_frame_boxes(page)

    # Framed block: the anchor baseline falls inside a colored card.
    containing = [b for b in boxes if b.y0 - 4 <= anchor_y <= b.y1 + 4]
    if containing:
        box = max(containing, key=lambda r: r.height)  # outermost border
        return frame_clip(box, page), "frame"

    # Unframed block: clip the text region from the label down to the next block.
    rect = noframe_clip(page, anchor_y, next_anchor_y, boxes)
    if rect is None:
        return None, "noframe clip failed"
    return rect, "noframe"


def build_next_anchor_index(blocks):
    """For each block id, the (page, y) of the next block in the same repo — used as
    the bottom boundary for unframed blocks. Block ids within a repo are emitted in
    source order, so the next array element is the next block on the page."""
    next_anchor = {}
    for i, block in enumerate(blocks):
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if not nxt or nxt.get("repo") != block.get("repo"):
            continue
        loc = nxt.get("pdfLocator")
        if loc and loc.get("page") and loc.get("y") is not None:
            next_anchor[block["id"]] = (int(loc["page"]), float(loc["y"]))
    return next_anchor


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing {INPUT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    blocks = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    changed, incremental = load_changed_set()
    existing_by_id = {}
    if incremental and OUTPUT_PATH.exists():
        try:
            prev = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            existing_by_id = {b["id"]: b for b in prev}
        except Exception:
            existing_by_id = {}
    can_reuse = incremental and bool(existing_by_id)

    next_anchor = build_next_anchor_index(blocks)

    updated = []
    docs = {}
    reason_counter = Counter()
    mode_counter = Counter()
    success_count = 0
    reused_count = 0

    for block in blocks:
        if can_reuse and block.get("repo") not in changed and block.get("id") in existing_by_id:
            # Unchanged repo: keep the prior preview entry verbatim; its PNG is already on disk.
            updated.append(existing_by_id[block["id"]])
            reused_count += 1
            continue

        kind = block.get("kind", "")
        if kind not in FRAME_KINDS:
            block["previewImage"] = None
            block["previewDebug"] = "non-frame block fallback to text"
            reason_counter[block["previewDebug"]] += 1
            updated.append(block)
            continue

        locator = block.get("pdfLocator")
        if not locator or not locator.get("page"):
            block["previewImage"] = None
            block["previewDebug"] = "missing pdfLocator"
            reason_counter[block["previewDebug"]] += 1
            updated.append(block)
            continue

        pdf_path = resolve_best_pdf_path(block)
        if not pdf_path:
            block["previewImage"] = None
            block["previewDebug"] = "no usable pdf found"
            reason_counter[block["previewDebug"]] += 1
            updated.append(block)
            continue

        try:
            pdf_key = str(pdf_path)
            if pdf_key not in docs:
                docs[pdf_key] = fitz.open(pdf_path)
            doc = docs[pdf_key]

            page_no = int(locator["page"])
            if page_no < 1 or page_no > doc.page_count:
                block["previewImage"] = None
                block["previewDebug"] = "locator page out of range"
                reason_counter[block["previewDebug"]] += 1
                updated.append(block)
                continue

            page = doc.load_page(page_no - 1)

            na = next_anchor.get(block["id"])
            next_anchor_y = na[1] if (na and na[0] == page_no) else None

            rect, mode = compute_clip(page, locator, next_anchor_y)
            if rect is None:
                block["previewImage"] = None
                block["previewDebug"] = mode
                reason_counter[mode] += 1
                updated.append(block)
                continue

            out_name = f"{block['id']}.png"
            out_path = OUTPUT_DIR / out_name
            page.get_pixmap(
                matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE), clip=rect, alpha=False
            ).save(out_path)

            block["previewImage"] = f"/public/search-previews/{out_name}"
            block["previewClip"] = {
                "page": page_no,
                "x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1,
            }
            block["previewDebug"] = mode
            mode_counter[mode] += 1
            success_count += 1

        except Exception as e:
            block["previewImage"] = None
            block["previewDebug"] = str(e)
            reason_counter[block["previewDebug"]] += 1

        updated.append(block)

    for doc in docs.values():
        doc.close()

    # `updated` is the complete current index, so any PNG it does not reference is an
    # orphan — left over from a deleted repo or from a changed repo whose block ids
    # shifted on re-render. Prune them so the preview dir cannot grow without bound.
    referenced = {Path(b["previewImage"]).name for b in updated if b.get("previewImage")}
    removed = 0
    for png in OUTPUT_DIR.glob("*.png"):
        if png.name not in referenced:
            png.unlink()
            removed += 1

    OUTPUT_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUTPUT_PATH}")
    print(f"incremental = {incremental}, reuse = {can_reuse}, reused = {reused_count}, "
          f"changed = {sorted(changed)}")
    print(f"preview success = {success_count}  (modes: {dict(mode_counter)})")
    print(f"orphan PNGs removed = {removed}")
    print(f"preview skip/failure reasons = {dict(reason_counter)}")


if __name__ == "__main__":
    main()
