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

if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)

WORK_DIR.mkdir()
OUTPUT_DIR.mkdir(exist_ok=True)

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

for repo in repos:
    name = repo["name"]

    if not name.lower().startswith("dx"):
        continue

    matched_repos += 1
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

    # 宽容编译
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

    books.append({
        "file": f"{name}.pdf",
        "title": name.replace("dx-", "").replace("-", " ").title(),
        "subtitle": "",
        "desc": "Auto-compiled from LaTeX"
    })

    compiled += 1


# 生成 books.json
with open("books.json", "w", encoding="utf-8") as f:
    json.dump(books, f, ensure_ascii=False, indent=2)

print("\n========== SUMMARY ==========")
print(f"Matched dx repos: {matched_repos}")
print(f"Compiled PDFs: {compiled}")
print("books.json generated.")
print("Done.")
