import json
import subprocess
from pathlib import Path

import fitz  # pip install pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "public" / "search-index.enriched.json"
OUTPUT_DIR = BASE_DIR / "public" / "search-previews"
OUTPUT_PATH = BASE_DIR / "public" / "search-index.previews.json"

ONLY_REPO = None

FRAME_KINDS = {
    "definition", "theorem", "example", "note", "remark",
    "proposition", "lemma", "corollary", "dxtips"
}

TEXT_LEFT = 72
TEXT_RIGHT_MARGIN = 72

TOP_PAD_BY_KIND = {
    "definition": 90,
    "theorem": 90,
    "example": 70,
    "note": 70,
    "remark": 70,
    "proposition": 90,
    "lemma": 90,
    "corollary": 90,
    "dxtips": 90,
}
BOTTOM_PAD_BY_KIND = {
    "definition": 32,
    "theorem": 32,
    "example": 28,
    "note": 28,
    "remark": 28,
    "proposition": 32,
    "lemma": 32,
    "corollary": 32,
    "dxtips": 32,
}


def pt_to_pdf_y(page_height: float, y_top_like: float, h: float) -> float:
    return max(0, page_height - y_top_like - h)


def parse_synctex_output(output: str):
    lines = output.splitlines()
    page = x = y = h = v = W = H = None
    for line in lines:
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
    if page is None:
        return None
    return {"page": page, "x": x, "y": y, "h": h, "v": v, "W": W, "H": H}


def synctex_view(synctex_path: Path, pdf_path: Path, source_path: str, line_no: int):
    synctex_dir = synctex_path.parent
    args = [
        "synctex", "view",
        "-i", f"{line_no}:1:{source_path}",
        "-o", str(pdf_path),
        "-d", str(synctex_dir),
    ]
    result = subprocess.run(args, capture_output=True, text=True, cwd=synctex_dir)
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return parse_synctex_output(output)


def resolve_best_pdf_path(block):
    debug_pdf_path = block.get("debugPdfPath")
    if debug_pdf_path and Path(debug_pdf_path).exists():
        return Path(debug_pdf_path)

    if block.get("synctex"):
        synctex_abs = Path(block["synctex"])
        synctex_dir = synctex_abs.parent
        main_pdf = synctex_dir / "main.pdf"
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
    updated = []

    for block in blocks:
        if ONLY_REPO and block.get("repo") != ONLY_REPO:
            updated.append(block)
            continue

        kind = block.get("kind", "")

        if kind not in FRAME_KINDS:
            block["previewImage"] = None
            block["previewDebug"] = "non-frame block fallback to text"
            updated.append(block)
            continue

        synctex_path = Path(block["synctex"]) if block.get("synctex") else None
        source_path = block.get("sourcePath")
        start_line = block.get("startLine")
        end_line = block.get("endLine")

        if not synctex_path or not synctex_path.exists() or not source_path or not start_line:
            block["previewImage"] = None
            block["previewDebug"] = "missing synctex/sourcePath/startLine"
            updated.append(block)
            continue

        pdf_path = resolve_best_pdf_path(block)
        if not pdf_path:
            block["previewImage"] = None
            block["previewDebug"] = "no usable pdf found"
            updated.append(block)
            continue

        try:
            start_loc = synctex_view(synctex_path, pdf_path, source_path, int(start_line))
            if not start_loc:
                block["previewImage"] = None
                block["previewDebug"] = "start synctex mapping failed"
                updated.append(block)
                continue

            if not end_line:
                block["previewImage"] = None
                block["previewDebug"] = "missing endLine for frame block"
                updated.append(block)
                continue

            end_loc = synctex_view(synctex_path, pdf_path, source_path, int(end_line))
            if not end_loc or int(end_loc["page"]) != int(start_loc["page"]):
                block["previewImage"] = None
                block["previewDebug"] = "end synctex mapping failed or cross-page block"
                updated.append(block)
                continue

            doc = fitz.open(pdf_path)
            page_index = int(start_loc["page"]) - 1
            page = doc.load_page(page_index)

            rect = make_block_rect(page, start_loc, end_loc, kind)

            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
            out_name = f"{block['id']}.png"
            out_path = OUTPUT_DIR / out_name
            pix.save(out_path)

            block["previewImage"] = f"public/search-previews/{out_name}"
            block["previewClip"] = {
                "page": start_loc["page"],
                "x0": rect.x0,
                "y0": rect.y0,
                "x1": rect.x1,
                "y1": rect.y1,
            }
            doc.close()

        except Exception as e:
            block["previewImage"] = None
            block["previewDebug"] = str(e)

        updated.append(block)

    OUTPUT_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()