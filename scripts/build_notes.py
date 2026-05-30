import os
import json
import requests
import subprocess
import shutil
import sys
from pathlib import Path

USERNAME = "yangminggulab"
TOKEN = os.getenv("GITHUB_TOKEN")
FORCE_REBUILD = os.getenv("FORCE_REBUILD", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent.parent
WORK_DIR = BASE_DIR / "temp_repos"
OUTPUT_DIR = BASE_DIR / "pdf"
STATE_FILE = BASE_DIR / "build_state.json"
NONNOTE_FILE = BASE_DIR / "build_nonnotes.json"
MANIFEST_FILE = BASE_DIR / "notes_manifest.json"
BOOKS_FILE = BASE_DIR / "books.json"

WORK_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def load_state(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# build_state.json tracks note repos (those that produce a PDF); build_nonnotes.json
# tracks dx* repos that have no main.tex. Both map repo name -> pushed_at.
state = load_state(STATE_FILE)
nonnotes = load_state(NONNOTE_FILE)


def write_github_output(needs_rebuild: bool):
    value = "true" if needs_rebuild else "false"
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"needs_rebuild={value}\n")
    print(f"[Output] needs_rebuild={value}")


def regenerate_videos():
    VIDEO_DIR = BASE_DIR / "video"
    VIDEOS_FILE = VIDEO_DIR / "videos.json"
    video_entries = []
    if VIDEO_DIR.exists():
        for vf in sorted(VIDEO_DIR.glob("*.mp4")):
            video_entries.append({"file": f"video/{vf.name}", "name": vf.name})
    with open(VIDEOS_FILE, "w", encoding="utf-8") as f:
        json.dump(video_entries, f, ensure_ascii=False, indent=2)
    return video_entries


print("Fetching repositories...")

headers = {"Accept": "application/vnd.github.v3+json"}
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

dx_repos = [r for r in repos if r["name"].lower().startswith("dx")]

# ── No-change early exit ─────────────────────────────────────────────────────
# Skip clone/compile/index/preview only if the set of dx* repos exactly matches
# what we recorded last time (notes + non-notes), none changed pushed_at, and every
# note still has its PDF. Non-note repos never produce output, so they are tracked
# only to avoid forcing a rebuild — they are not required to have a PDF.
if not FORCE_REBUILD:
    api = {r["name"]: r["pushed_at"] for r in dx_repos}
    known = set(state) | set(nonnotes)
    all_unchanged = (
        set(api) == known
        and all(state.get(n) == api.get(n) for n in state)
        and all(nonnotes.get(n) == api.get(n) for n in nonnotes)
        and all((OUTPUT_DIR / f"{n}.pdf").exists() for n in state)
    )
    if all_unchanged:
        print("No repository changes detected — skipping clone, compile, and index.")
        video_entries = regenerate_videos()
        write_github_output(needs_rebuild=False)
        print("\n========== SUMMARY ==========")
        print(f"Matched dx repos: {len(dx_repos)} "
              f"({len(state)} notes, {len(nonnotes)} non-notes, all unchanged, early exit)")
        print(f"videos.json: {len(video_entries)} videos found")
        print("Done.")
        sys.exit(0)

# ── Full build ────────────────────────────────────────────────────────────────
matched_repos = 0
compiled = 0
books = []
manifest = []
note_names = set()
nonnote_names = set()

for repo in dx_repos:
    name = repo["name"]
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
            )
            print("  -> cloned")
        except subprocess.CalledProcessError:
            print("  -> clone failed")
            continue
    else:
        print("  -> repo exists, pulling latest")
        subprocess.run(["git", "fetch", "--depth", "1", "origin"], cwd=repo_path, check=False)
        subprocess.run(["git", "reset", "--hard", "origin/HEAD"], cwd=repo_path, check=False)

    main_candidates = list(repo_path.rglob("main.tex"))
    if not main_candidates:
        print("  -> no main.tex found (non-note repo, tracked in build_nonnotes.json)")
        nonnotes[name] = latest_commit
        nonnote_names.add(name)
        continue

    note_names.add(name)

    print("  -> main.tex candidates:")
    for p in main_candidates:
        print(f"     {p}")

    main_tex = main_candidates[0]
    tex_dir = main_tex.parent
    pdf_name = f"{name}.pdf"

    print(f"  -> selected main.tex: {main_tex}")

    pdf_candidates = [
        tex_dir / f"{main_tex.stem}.pdf",
        tex_dir / "main.pdf",
    ]
    existing_pdf_path = next((p for p in pdf_candidates if p.exists()), None)
    existing_synctex = list(tex_dir.glob("*.synctex.gz"))

    need_compile = (
            FORCE_REBUILD
            or not (name in state and state[name] == latest_commit)
            or existing_pdf_path is None
            or len(existing_synctex) == 0
    )

    if need_compile:
        print(f"  -> compiling {main_tex}")
        print(f"  -> main.tex first 10 lines:")
        try:
            for i, line in enumerate(main_tex.read_text(errors="replace").splitlines()[:10], 1):
                print(f"     {i}: {line}")
        except Exception as e:
            print(f"     (could not read: {e})")

        log_path = tex_dir / "build.log"
        with open(log_path, "w") as log_f:
            result = subprocess.run(
                [
                    "latexmk",
                    "-xelatex",
                    "-synctex=1",
                    "-interaction=nonstopmode",
                    "-f",
                    main_tex.name,
                ],
                cwd=tex_dir,
                check=False,
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )
        print(f"  -> latexmk exit code: {result.returncode}")
        if result.returncode != 0:
            log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
            main_log = tex_dir / "main.log"
            if main_log.exists():
                log_text = main_log.read_text(errors="replace")
                print("  -> COMPILE FAILED, last 60 lines of main.log:")
                for line in log_text.splitlines()[-60:]:
                    print(f"     {line}")
            elif log_text:
                print("  -> COMPILE FAILED, last 40 lines of build.log:")
                for line in log_text.splitlines()[-40:]:
                    print(f"     {line}")
            else:
                print("  -> COMPILE FAILED, no log file produced (xelatex crashed at startup)")
        compiled += 1
    else:
        print("  -> no update, skipping compile")

    print("  -> files after compile/check:")
    for p in sorted(tex_dir.iterdir()):
        if p.is_file() and (
            p.suffix == ".pdf"
            or p.suffix == ".tex"
            or ".synctex" in p.name
        ):
            print(f"     {p.name}")

    pdf_candidates = [
        tex_dir / f"{main_tex.stem}.pdf",
        tex_dir / "main.pdf",
    ]
    pdf_path = next((p for p in pdf_candidates if p.exists()), None)

    synctex_candidates = list(tex_dir.glob("*.synctex.gz"))
    print("  -> synctex candidates found:")
    for p in synctex_candidates:
        print(f"     {p.name}")

    synctex_path = None
    preferred_names = [
        f"{main_tex.name}.synctex.gz",
        f"{main_tex.stem}.synctex.gz",
    ]
    for pref in preferred_names:
        candidate = tex_dir / pref
        if candidate.exists():
            synctex_path = candidate
            break
    if synctex_path is None and synctex_candidates:
        synctex_path = synctex_candidates[0]

    manifest_item = {
        "repo": name,
        "title": name.replace("dx-", "").replace("-", " ").title(),
        "pdf": f"pdf/{pdf_name}",
        "main_tex": str(main_tex),
        "synctex": str(synctex_path) if synctex_path else None,
    }
    manifest.append(manifest_item)

    if pdf_path and pdf_path.exists():
        output_pdf = OUTPUT_DIR / pdf_name
        shutil.copy(pdf_path, output_pdf)
        print(f"  -> saved to {output_pdf}")
        state[name] = latest_commit
    else:
        print("  -> pdf not produced")
        continue

    if synctex_path and synctex_path.exists():
        print(f"  -> synctex chosen: {synctex_path.name}")
    else:
        print("  -> warning: synctex not produced")

    books.append({
        "file": pdf_name,
        "title": name.replace("dx-", "").replace("-", " ").title(),
        "subtitle": "",
        "desc": "Auto-compiled from LaTeX",
    })

# Clean up state: keep only entries for repos that still exist in each category.
# A repo can move between categories (e.g. gains/loses main.tex), so prune both.
state = {k: v for k, v in state.items() if k in note_names}
nonnotes = {k: v for k, v in nonnotes.items() if k in nonnote_names}

# Clean up orphaned PDFs: remove PDFs whose note repo no longer exists
current_pdf_names = {f"{name}.pdf" for name in note_names}
for pdf_file in OUTPUT_DIR.glob("*.pdf"):
    if pdf_file.name not in current_pdf_names:
        print(f"  -> removing orphaned PDF: {pdf_file.name}")
        pdf_file.unlink()

books.sort(key=lambda x: x["title"].lower())
manifest.sort(key=lambda x: x["title"].lower())

with open(BOOKS_FILE, "w", encoding="utf-8") as f:
    json.dump(books, f, ensure_ascii=False, indent=2)

with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

with open(NONNOTE_FILE, "w", encoding="utf-8") as f:
    json.dump(nonnotes, f, ensure_ascii=False, indent=2)

with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

video_entries = regenerate_videos()

write_github_output(needs_rebuild=True)

print("\n========== SUMMARY ==========")
print(f"Matched dx repos: {matched_repos} ({len(note_names)} notes, {len(nonnote_names)} non-notes)")
print(f"Compiled PDFs: {compiled}")
print(f"Manifest entries: {len(manifest)}")
print(f"books.json generated at: {BOOKS_FILE}")
print(f"build_state.json generated at: {STATE_FILE} ({len(state)} notes)")
print(f"build_nonnotes.json generated at: {NONNOTE_FILE} ({len(nonnotes)} non-notes)")
print(f"notes_manifest.json generated at: {MANIFEST_FILE}")
print(f"videos.json: {len(video_entries)} videos found")
print("Done.")
