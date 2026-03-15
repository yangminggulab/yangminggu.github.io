import requests
import subprocess
import os
import shutil
from pathlib import Path

USERNAME = "yangminggulab"

PDF_DIR = Path("pdf")
PDF_DIR.mkdir(exist_ok=True)

WORK_DIR = Path("temp_repos")

if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)

WORK_DIR.mkdir()

print("Fetching repositories...")

url = f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100"
repos = requests.get(url).json()

for repo in repos:

    name = repo["name"]

    if not name.startswith("dx"):
        continue

    clone_url = repo["clone_url"]

    print(f"\nProcessing {name}")

    repo_path = WORK_DIR / name

    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
        check=True
    )

    main_tex = repo_path / "main.tex"

    if not main_tex.exists():
        print("No main.tex found, skipping")
        continue

    print("Compiling LaTeX...")

    subprocess.run(
        [
            "latexmk",
            "-xelatex",
            "-interaction=nonstopmode",
            "main.tex"
        ],
        cwd=repo_path,
        check=True
    )

    pdf_file = repo_path / "main.pdf"

    if pdf_file.exists():

        target = PDF_DIR / f"{name}.pdf"

        shutil.copy(pdf_file, target)

        print(f"PDF saved to {target}")

    else:
        print("Compilation finished but PDF not found")

print("\nAll done.")
