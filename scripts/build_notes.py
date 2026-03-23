import os
import json
import requests
import subprocess
import shutil
from pathlib import Path

USERNAME = "yangminggulab"
TOKEN = os.getenv("GITHUB_TOKEN")

# 这个脚本负责：
# 1. 拉取/复用本地 dx 仓库
# 2. 编译 main.tex 为 PDF
# 3. 生成 books.json / build_state.json / notes_manifest.json
# 4. 现在额外开启 SyncTeX，给后面做 source -> PDF 定位做准备

BASE_DIR = Path(__file__).resolve().parent.parent

WORK_DIR = BASE_DIR / "temp_repos"
OUTPUT_DIR = BASE_DIR / "pdf"
STATE_FILE = BASE_DIR / "build_state.json"
MANIFEST_FILE = BASE_DIR / "notes_manifest.json"
BOOKS_FILE = BASE_DIR / "books.json"

WORK_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

if STATE_FILE.exists():
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
else:
    state = {}

print("Fetching repositories...")

headers = {
    "Accept": "application/vnd.github.v3+json",
}

if TOKEN:
    headers["Authorization"] = f"token {TOKEN}"

repos = []
page = 1

while True:
    url = f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100&page={page}"
    response = requests.get(url, headers=headers, timeout=30)
    page_data = response.json()

    if isinstance(page_data, dict) and "message" in page_data:
        print("GitHub API error:")
        print(page_data)
        break

    if not page_data:
        break

    repos.extend(page_data)
    page += 1

matched_repos = 0
compiled = 0
books = []
manifest = []

existing_books = {}
for pdf_file in OUTPUT_DIR.glob("*.pdf"):
    existing_books[pdf_file.name] = {
        "file": pdf_file.name,
        "title": pdf_file.stem.replace("dx-", "").replace("-", " ").title(),
        "subtitle": "",
        "desc": "Auto-compiled from LaTeX"
    }

for repo in repos:
    name = repo["name"]

    if not name.lower().startswith("dx"):
        continue

    matched_repos += 1
    latest_commit = repo["pushed_at"]

    clone_url = repo["clone_url"]
    repo_path = WORK_DIR / name

    print(f"\n[Repo] {name}")

    if not repo_path.exists():
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("  -> cloned")
        except subprocess.CalledProcessError:
            print("  -> clone failed")
            continue
    else:
        print("  -> repo already exists, reuse local copy")

    main_candidates = list(repo_path.rglob("main.tex"))

    if not main_candidates:
        print("  -> no main.tex found")
        continue

    print("  -> main.tex candidates:")
    for p in main_candidates:
        print(f"     {p}")

    main_tex = main_candidates[0]
    tex_dir = main_tex.parent

    print(f"  -> selected main.tex: {main_tex}")

    pdf_name = f"{name}.pdf"

    # 先预设 synctex 路径，后面编译后会生成
    synctex_path = main_tex.with_suffix(".synctex.gz")

    manifest_item = {
        "repo": name,
        "title": name.replace("dx-", "").replace("-", " ").title(),
        "pdf": f"pdf/{pdf_name}",
        "main_tex": str(main_tex),
        "synctex": str(synctex_path),
    }
    manifest.append(manifest_item)

    if name in state and state[name] == latest_commit:
        print("  -> no update, skipping compile")
        if pdf_name in existing_books:
            books.append(existing_books[pdf_name])
        else:
            books.append({
                "file": pdf_name,
                "title": name.replace("dx-", "").replace("-", " ").title(),
                "subtitle": "",
                "desc": "Auto-compiled from LaTeX"
            })
        continue

    print(f"  -> compiling {main_tex}")

    subprocess.run(
        [
            "latexmk",
            "-xelatex",
            "-synctex=1",
            "-interaction=nonstopmode",
            "-f",
            main_tex.name
        ],
        cwd=tex_dir
    )

    pdf_path = main_tex.with_suffix(".pdf")
    synctex_path = main_tex.with_suffix(".synctex.gz")

    if not pdf_path.exists():
        print("  -> pdf not produced")
        continue

    output_pdf = OUTPUT_DIR / pdf_name
    shutil.copy(pdf_path, output_pdf)

    print(f"  -> saved to {output_pdf}")

    if synctex_path.exists():
        print(f"  -> synctex generated: {synctex_path.name}")
    else:
        print("  -> warning: synctex not produced")

    book_info = {
        "file": pdf_name,
        "title": name.replace("dx-", "").replace("-", " ").title(),
        "subtitle": "",
        "desc": "Auto-compiled from LaTeX"
    }

    books.append(book_info)
    state[name] = latest_commit
    compiled += 1

existing_names = {book["file"] for book in books}
for pdf_name, book_info in existing_books.items():
    if pdf_name not in existing_names:
        books.append(book_info)

books.sort(key=lambda x: x["title"].lower())
manifest.sort(key=lambda x: x["title"].lower())

with open(BOOKS_FILE, "w", encoding="utf-8") as f:
    json.dump(books, f, ensure_ascii=False, indent=2)

with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print("\n========== SUMMARY ==========")
print(f"Matched dx repos: {matched_repos}")
print(f"Compiled PDFs: {compiled}")
print(f"Manifest entries: {len(manifest)}")
print(f"books.json generated at: {BOOKS_FILE}")
print(f"build_state.json generated at: {STATE_FILE}")
print(f"notes_manifest.json generated at: {MANIFEST_FILE}")
print("Done.")