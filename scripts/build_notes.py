import os
import requests
import subprocess
import shutil
from pathlib import Path

USERNAME = "yangminggulab"
TOKEN = os.getenv("GITHUB_TOKEN")  # 本地或 GitHub Actions 里设置环境变量

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
        print("  -> clone failed, skipping")
        continue

    main_candidates = list(repo_path.rglob("main.tex"))

    if not main_candidates:
        print("  -> no main.tex found, skipping")
        continue

    main_tex = main_candidates[0]
    tex_dir = main_tex.parent

    print(f"  -> found main.tex at: {main_tex.relative_to(repo_path)}")
    print(f"  -> compiling {main_tex.name}")

    # 宽容点：
    # 1. 用 -f
    # 2. 不用 check=True
    # 3. 只要最后真的生成 pdf 就算成功
    result = subprocess.run(
        [
            "latexmk",
            "-xelatex",
            "-interaction=nonstopmode",
            "-f",
            main_tex.name
        ],
        cwd=tex_dir,
    )

    pdf_path = main_tex.with_suffix(".pdf")

    if pdf_path.exists():
        output_pdf = OUTPUT_DIR / f"{name}.pdf"
        shutil.copy(pdf_path, output_pdf)
        print(f"  -> saved to {output_pdf}")
        compiled += 1
    else:
        print(f"  -> compile failed (return code {result.returncode}), skipping")

print("\n========== SUMMARY ==========")
print(f"Matched dx repos: {matched_repos}")
print(f"Compiled PDFs: {compiled}")
print("Done.")
