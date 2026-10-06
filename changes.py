"""Collect what actually changed in a git repository."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MAX_DIFF_CHARS = 300_000
MAX_UNTRACKED_BYTES = 100_000
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class GitError(Exception):
    pass


@dataclass
class ChangeSet:
    diff: str
    files: list[str]
    commits: list[str]
    mode: str
    warnings: list[str] = field(default_factory=list)


def git(repo: Path, *args: str, check: bool = True) -> str:
    # UTF-8 explicitly: Windows defaults to cp1251 and crashes on Cyrillic or emoji.
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def is_git_repo(repo: Path) -> bool:
    try:
        return git(repo, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except (GitError, OSError):
        return False


def _has_commits(repo: Path) -> bool:
    return bool(git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False).strip())


def _untracked(repo: Path) -> tuple[str, list[str]]:
    paths = [p for p in git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    chunks = []
    for rel in paths:
        path = repo / rel
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_UNTRACKED_BYTES or b"\0" in raw[:8000]:
            chunks.append(f"+++ new file: {rel} (binary or too large, content skipped)\n")
            continue
        text = raw.decode("utf-8", errors="replace")
        body = "".join(f"+{line}\n" for line in text.splitlines())
        chunks.append(f"+++ new file: {rel}\n{body}")
    return "".join(chunks), paths


def collect_changes(repo_path: str, session_start: str | None = None) -> ChangeSet:
    repo = Path(repo_path)
    warnings: list[str] = []

    top = Path(git(repo, "rev-parse", "--show-toplevel").strip())
    if top.resolve() != repo.resolve():
        warnings.append(f"This folder is inside the repository at {top}; checking the whole repository.")
        repo = top

    if not _has_commits(repo):
        base, mode = EMPTY_TREE, "everything (repository has no commits)"
    elif session_start:
        session_start = session_start.replace("T", " ", 1)
        base = git(repo, "rev-list", "-1", f"--before={session_start}", "HEAD").strip() or EMPTY_TREE
        mode = f"all changes since {session_start}"
    elif git(repo, "status", "--porcelain").strip():
        base, mode = "HEAD", "uncommitted changes vs last commit"
    else:
        parent = git(repo, "rev-parse", "--verify", "-q", "HEAD~1", check=False).strip()
        base = parent or EMPTY_TREE
        mode = "last commit vs previous commit"

    if mode == "last commit vs previous commit":
        diff = git(repo, "diff", base, "HEAD")
        files = [f for f in git(repo, "diff", "--name-only", base, "HEAD").splitlines() if f]
        untracked_diff, untracked = "", []
    else:
        diff = git(repo, "diff", base)
        files = [f for f in git(repo, "diff", "--name-only", base).splitlines() if f]
        untracked_diff, untracked = _untracked(repo)

    diff += untracked_diff
    files += [f for f in untracked if f not in files]

    commits = []
    if _has_commits(repo) and base != "HEAD":
        rng = "HEAD" if base == EMPTY_TREE else f"{base}..HEAD"
        commits = [c for c in git(repo, "log", "--oneline", rng).splitlines() if c]

    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS]
        warnings.append("Diff too large, some claims may be unverifiable.")
    if not diff.strip():
        warnings.append("No changes found for this period.")

    return ChangeSet(diff=diff, files=files, commits=commits, mode=mode, warnings=warnings)
