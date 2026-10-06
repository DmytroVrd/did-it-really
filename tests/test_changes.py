import os
import subprocess

import pytest

from changes import MAX_DIFF_CHARS, collect_changes, is_git_repo


def run(repo, *args, date=None):
    env = {**os.environ}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def commit(repo, name, content, date):
    (repo / name).write_text(content, encoding="utf-8")
    run(repo, "add", name)
    run(repo, "commit", "-q", "-m", f"edit {name}", date=date)


@pytest.fixture
def repo(tmp_path):
    run(tmp_path, "init", "-q")
    run(tmp_path, "config", "user.email", "test@example.com")
    run(tmp_path, "config", "user.name", "Test")
    run(tmp_path, "config", "core.autocrlf", "false")
    commit(tmp_path, "base.py", "x = 1\n", "2026-01-01T09:00:00")
    return tmp_path


def test_not_a_repo(tmp_path, monkeypatch):
    # Stop git from finding a repository in a parent folder (e.g. an accidental repo in the home folder).
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert not is_git_repo(tmp_path)


def test_subfolder_warns_about_whole_repo(repo):
    (repo / "sub").mkdir()
    (repo / "sub" / "s.py").write_text("s = 1\n", encoding="utf-8")
    c = collect_changes(str(repo / "sub"))
    assert any("inside the repository at" in w for w in c.warnings)
    assert c.files == ["sub/s.py"]
    assert "+s = 1" in c.diff


def test_uncommitted_changes_and_untracked_files(repo):
    (repo / "base.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "new.py").write_text("y = 3\n", encoding="utf-8")
    c = collect_changes(str(repo))
    assert c.mode == "uncommitted changes vs last commit"
    assert "+x = 2" in c.diff and "+y = 3" in c.diff
    assert sorted(c.files) == ["base.py", "new.py"]


def test_clean_repo_uses_last_commit(repo):
    commit(repo, "a.py", "a = 1\n", "2026-01-01T10:00:00")
    c = collect_changes(str(repo))
    assert c.mode == "last commit vs previous commit"
    assert c.files == ["a.py"]
    assert "base.py" not in c.diff


def test_session_start_includes_every_commit_after_it(repo):
    commit(repo, "a.py", "a = 1\n", "2026-01-01T10:00:00")
    commit(repo, "b.py", "b = 1\n", "2026-01-01T10:30:00")
    commit(repo, "c.py", "c = 1\n", "2026-01-01T11:00:00")
    (repo / "d.py").write_text("d = 1\n", encoding="utf-8")
    c = collect_changes(str(repo), "2026-01-01T09:30")
    assert sorted(c.files) == ["a.py", "b.py", "c.py", "d.py"]
    assert len(c.commits) == 3
    assert "base.py" not in c.files


def test_session_start_before_first_commit_includes_everything(repo):
    c = collect_changes(str(repo), "2025-12-31T00:00")
    assert c.files == ["base.py"]


def test_no_changes_warning(repo):
    c = collect_changes(str(repo), "2027-01-01T00:00")
    assert c.diff == ""
    assert "No changes found for this period." in c.warnings


def test_cyrillic_and_emoji_do_not_crash(repo):
    # Cyrillic + emoji written as escapes: the source stays ASCII, the file content does not.
    text = "\u041f\u0440\u0438\u0432\u0456\u0442 \U0001F680"
    (repo / "base.py").write_text(f'msg = "{text}"\n', encoding="utf-8")
    c = collect_changes(str(repo))
    assert text in c.diff


def test_huge_diff_is_capped_with_warning(repo):
    (repo / "big.txt").write_text("line of text\n" * 30_000, encoding="utf-8")
    run(repo, "add", "big.txt")
    c = collect_changes(str(repo))
    assert len(c.diff) == MAX_DIFF_CHARS
    assert any("too large" in w for w in c.warnings)
