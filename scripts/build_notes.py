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

    # 更宽松：只要是 dx 开头就处理
    if not name.lower().startswith("dx"):
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

    # 递归搜索 main.tex，而不是只看根目录
    main_candidates = list(repo_path.rglob("main.tex"))

    if not main_candidates:
        print("No main.tex found, skipping")
        continue

    # 先用找到的第一个 main.tex
    main_tex = main_candidates[0]
    tex_dir = main_tex.parent

    print(f"Found main.tex at: {main_tex.relative_to(repo_path)}")
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
        cwd=tex_dir
    )

    if result.returncode != 0:
        print(f"LaTeX compilation failed for {name}, skipping")
        continue

    pdf_file = tex_dir / "main.pdf"

    # 即使编译命令跑过，也可能没生成 PDF
    if pdf_file.exists():
        target = PDF_DIR / f"{name}.pdf"
        shutil.copy(pdf_file, target)
        print(f"PDF saved to {target}")
    else:
        print(f"No PDF generated for {name}, skipping")

print("\nAll done.")
