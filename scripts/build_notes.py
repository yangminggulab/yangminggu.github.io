import os
import json
import requests
import subprocess
import shutil
from pathlib import Path

USERNAME = "yangminggulab"
TOKEN = os.getenv("GITHUB_TOKEN")

WORK_DIR = Path("temp_repos")
OUTPUT_DIR = Path("pdf")
STATE_FILE = Path("build_state.json")

if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)

WORK_DIR.mkdir()
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

# 先读取已有 pdf，避免没更新的书从书架消失
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

    # 没更新就跳过编译，但保留书架信息
    if name in state and state[name] == latest_commit:
        print(f"\n[Repo] {name}")
        print("  -> no update, skipping compile")
        pdf_name = f"{name}.pdf"
        if pdf_name in existing_books:
            books.append(existing_books[pdf_name])
        continue

    clone_url = repo["clone_url"]
    repo_path = WORK_DIR / name

    print(f"\n[Repo] {name}")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print("  -> clone failed")
        continue

    main_candidates = list(repo_path.rglob("main.tex"))

    if not main_candidates:
        print("  -> no main.tex found")
        continue

    main_tex = main_candidates[0]
    tex_dir = main_tex.parent

    print(f"  -> compiling {main_tex}")

    # 宽容编译：只要最后真生成 pdf 就算成功
    subprocess.run(
        [
            "latexmk",
            "-xelatex",
            "-interaction=nonstopmode",
            "-f",
            main_tex.name
        ],
        cwd=tex_dir
    )

    pdf_path = main_tex.with_suffix(".pdf")

    if not pdf_path.exists():
        print("  -> pdf not produced")
        continue

    output_pdf = OUTPUT_DIR / f"{name}.pdf"
    shutil.copy(pdf_path, output_pdf)

    print(f"  -> saved to {output_pdf}")

    book_info = {
        "file": f"{name}.pdf",
        "title": name.replace("dx-", "").replace("-", " ").title(),
        "subtitle": "",
        "desc": "Auto-compiled from LaTeX"
    }

    books.append(book_info)
    state[name] = latest_commit
    compiled += 1

# 把那些本次没更新、但已有 pdf 的书也补进书架
existing_names = {book["file"] for book in books}
for pdf_name, book_info in existing_books.items():
    if pdf_name not in existing_names:
        books.append(book_info)

# 按标题排序
books.sort(key=lambda x: x["title"].lower())

with open("books.json", "w", encoding="utf-8") as f:
    json.dump(books, f, ensure_ascii=False, indent=2)

with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("\n========== SUMMARY ==========")
print(f"Matched dx repos: {matched_repos}")
print(f"Compiled PDFs: {compiled}")
print("books.json generated.")
print("build_state.json generated.")
print("Done.")
