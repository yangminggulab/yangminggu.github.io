import requests
import subprocess
import shutil
from pathlib import Path

USERNAME = "yangminggulab"

PDF_DIR = Path("pdf")
PDF_DIR.mkdir(exist_ok=True)

WORK_DIR = Path("temp_repos")

# 每次运行前清空临时目录
if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)
WORK_DIR.mkdir()

print("Fetching repositories...")

url = f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100"
repos = requests.get(url).json()

for repo in repos:
    name = repo["name"]

    # 只处理 dx- 开头的仓库
    if not name.startswith("dx-"):
        continue

    clone_url = repo["clone_url"]
    repo_path = WORK_DIR / name

    print(f"\nProcessing {name}")

    # 克隆仓库：失败就跳过
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
            check=True
        )
    except subprocess.CalledProcessError:
        print(f"Failed to clone {name}, skipping")
        continue

    main_tex = repo_path / "main.tex"

    # 没有 main.tex 就跳过
    if not main_tex.exists():
        print("No main.tex found, skipping")
        continue

    print("Compiling LaTeX...")

    # LaTeX 编译：宽容模式
    result = subprocess.run(
        [
            "latexmk",
            "-xelatex",
            "-interaction=nonstopmode",
            "-f",
            "main.tex"
        ],
        cwd=repo_path
    )

    if result.returncode != 0:
        print(f"LaTeX compilation failed for {name}, skipping")
        continue

    pdf_file = repo_path / "main.pdf"

    # 即使编译命令跑过，也可能没生成 PDF
    if pdf_file.exists():
        target = PDF_DIR / f"{name}.pdf"
        shutil.copy(pdf_file, target)
        print(f"PDF saved to {target}")
    else:
        print(f"No PDF generated for {name}, skipping")

print("\nAll done.")
