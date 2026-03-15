import requests
import subprocess
import shutil
from pathlib import Path

USERNAME = "yangminggulab"

WORK_DIR = Path("temp_repos")

# 每次运行前清空临时目录
if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)
WORK_DIR.mkdir()

print("Fetching repositories...")

url = f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100"
repos = requests.get(url, timeout=30).json()

matched_repos = 0
found_main = 0

for repo in repos:
    name = repo["name"]

    # 只处理 dx 开头的仓库
    if not name.lower().startswith("dx"):
        continue

    matched_repos += 1
    clone_url = repo["clone_url"]
    repo_path = WORK_DIR / name

    print(f"\n[Repo] {name}")

    # 克隆仓库
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

    # 递归搜索 main.tex
    main_candidates = list(repo_path.rglob("main.tex"))

    if not main_candidates:
        print("  -> no main.tex found")
        continue

    found_main += 1
    print("  -> found main.tex at:")
    for p in main_candidates:
        print(f"     {p.relative_to(repo_path)}")

print("\n========== SUMMARY ==========")
print(f"Matched dx repos: {matched_repos}")
print(f"Repos with main.tex: {found_main}")
print("Check finished.")
