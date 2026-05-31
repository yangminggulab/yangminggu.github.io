import json
import subprocess
from collections import Counter
from pathlib import Path

import fitz

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "public" / "search-index.enriched.json"
OUTPUT_DIR = BASE_DIR / "public" / "search-previews"
OUTPUT_PATH = BASE_DIR / "public" / "search-index.previews.json"
CHANGED_FILE = BASE_DIR / "build_changed.json"

FRAME_KINDS = {
    "definition", "theorem", "example", "note", "remark",
    "proposition", "lemma", "corollary", "dxtips"
}

TEXT_LEFT = 72
TEXT_RIGHT_MARGIN = 72

TOP_PAD_BY_KIND = {
    "definition": 90, "theorem": 90, "example": 70, "note": 70,
    "remark": 70, "proposition": 90, "lemma": 90, "corollary": 90, "dxtips": 90,
}
BOTTOM_PAD_BY_KIND = {
    "definition": 32, "theorem": 32, "example": 28, "note": 28,
    "remark": 28, "proposition": 32, "lemma": 32, "corollary": 32, "dxtips": 32,
}


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


def pt_to_pdf_y(page_height: float, y_top_like: float, h: float) -> float:
    return max(0, page_height - y_top_like - h)


def parse_synctex_output(output: str):
    chunks = output.split("Output:")
    results = []
    for chunk in chunks[1:]:
        page = x = y = h = v = W = H = None
        for line in chunk.splitlines():
            s = line.strip()
            if s.startswith("Page:"):
                page = int(s.split(":", 1)[1].strip())
            elif s.startswith("x:"):
                x = float(s.split(":", 1)[1].strip())
            elif s.startswith("y:"):
                y = float(s.split(":", 1)[1].strip())
            elif s.startswith("h:"):
                h = float(s.split(":", 1)[1].strip())
            elif s.startswith("v:"):
                v = float(s.split(":", 1)[1].strip())
            elif s.startswith("W:"):
                W = float(s.split(":", 1)[1].strip())
            elif s.startswith("H:"):
                H = float(s.split(":", 1)[1].strip())
        if page is not None:
            results.append({"page": page, "x": x, "y": y, "h": h, "v": v, "W": W, "H": H})
    return results[0] if results else None


def synctex_view(synctex_path: Path, pdf_path: Path, source_path: str, line_no: int):
    result = subprocess.run(
        [
            "synctex", "view",
            "-i", f"{line_no}:1:{source_path}",
            "-o", str(pdf_path),
            "-d", str(synctex_path.parent),
        ],
        capture_output=True,
        text=True,
        cwd=synctex_path.parent,
    )
    return parse_synctex_output((result.stdout or "") + "\n" + (result.stderr or ""))


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


def make_block_rect(page, start_loc, end_loc, kind):
    start_y = float(start_loc.get("y") or start_loc.get("v") or 0)
    start_h = float(start_loc.get("H") or start_loc.get("h") or 16)
    end_y = float(end_loc.get("y") or end_loc.get("v") or 0)
    end_h = float(end_loc.get("H") or end_loc.get("h") or 16)

    start_top = pt_to_pdf_y(page.rect.height, start_y, start_h)
    end_top = pt_to_pdf_y(page.rect.height, end_y, end_h)

    top = min(start_top, end_top) - TOP_PAD_BY_KIND.get(kind, 70)
    bottom = max(start_top + start_h, end_top + end_h) + BOTTOM_PAD_BY_KIND.get(kind, 28)

    rect = fitz.Rect(
        max(0, TEXT_LEFT),
        max(0, top),
        min(page.rect.width, page.rect.width - TEXT_RIGHT_MARGIN),
        min(page.rect.height, bottom),
    )

    if rect.height < 140:
        rect.y1 = min(page.rect.height, rect.y0 + 160)

    return rect


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

    updated = []
    docs = {}
    reason_counter = Counter()
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

        synctex = block.get("synctex")
        source_path = block.get("sourcePath")
        start_line = block.get("startLine")
        end_line = block.get("endLine")

        synctex_path = Path(synctex) if synctex else None
        if not synctex_path or not synctex_path.exists() or not source_path or not start_line:
            block["previewImage"] = None
            block["previewDebug"] = "missing synctex/sourcePath/startLine"
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
            start_loc = synctex_view(synctex_path, pdf_path, source_path, int(start_line))
            if not start_loc:
                block["previewImage"] = None
                block["previewDebug"] = "start synctex mapping failed"
                reason_counter[block["previewDebug"]] += 1
                updated.append(block)
                continue

            if not end_line:
                block["previewImage"] = None
                block["previewDebug"] = "missing endLine for frame block"
                reason_counter[block["previewDebug"]] += 1
                updated.append(block)
                continue

            end_loc = synctex_view(synctex_path, pdf_path, source_path, int(end_line))
            if not end_loc or int(end_loc["page"]) != int(start_loc["page"]):
                block["previewImage"] = None
                block["previewDebug"] = "end synctex mapping failed or cross-page block"
                reason_counter[block["previewDebug"]] += 1
                updated.append(block)
                continue

            pdf_key = str(pdf_path)
            if pdf_key not in docs:
                docs[pdf_key] = fitz.open(pdf_path)

            doc = docs[pdf_key]
            page = doc.load_page(int(start_loc["page"]) - 1)
            rect = make_block_rect(page, start_loc, end_loc, kind)

            out_name = f"{block['id']}.png"
            out_path = OUTPUT_DIR / out_name
            page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False).save(out_path)

            block["previewImage"] = f"/public/search-previews/{out_name}"
            block["previewClip"] = {
                "page": start_loc["page"],
                "x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1,
            }
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
    print(f"preview success = {success_count}")
    print(f"orphan PNGs removed = {removed}")
    print(f"preview failure reasons = {dict(reason_counter)}")


if __name__ == "__main__":
    main()