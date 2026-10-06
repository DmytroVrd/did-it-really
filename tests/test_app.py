import subprocess

import pytest

import verifier
from app import app


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def repo(tmp_path):
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("a = 2\n", encoding="utf-8")
    return tmp_path


def post(client, **body):
    r = client.post("/api/check", json=body)
    return r.status_code, r.get_json()


def test_empty_report(client):
    assert post(client, report=" ", repo_path="x") == (400, {"error": "Paste the agent's report first.", "field": "report"})


def test_empty_path(client):
    code, data = post(client, report="did it", repo_path="")
    assert (code, data["field"]) == (400, "repo_path")


def test_missing_folder(client, tmp_path):
    code, data = post(client, report="did it", repo_path=str(tmp_path / "nope"))
    assert (code, data["error"]) == (400, "This folder does not exist.")


def test_not_a_git_repo(client, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    code, data = post(client, report="did it", repo_path=str(tmp_path))
    assert (code, data["error"]) == (400, "There is no git repository in this folder.")


def test_quoted_path_is_accepted(client, repo, monkeypatch):
    monkeypatch.setattr(verifier, "ask_gemini", lambda r, c: [])
    code, data = post(client, report="did it", repo_path=f'"{repo}"')
    assert code == 422  # got past path validation


def test_missing_api_key(client, repo, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code, data = post(client, report="Changed a.py", repo_path=str(repo))
    assert code == 502
    assert "GEMINI_API_KEY is not set" in data["error"]


def test_rate_limit_message(client, repo, monkeypatch):
    def boom(report, changes):
        raise verifier.AIError(verifier._friendly(Exception("429 RESOURCE_EXHAUSTED")))
    monkeypatch.setattr(verifier, "ask_gemini", boom)
    code, data = post(client, report="Changed a.py", repo_path=str(repo))
    assert code == 502 and "rate limit" in data["error"]


def test_no_claims(client, repo, monkeypatch):
    monkeypatch.setattr(verifier, "ask_gemini", lambda r, c: [])
    code, data = post(client, report="hello", repo_path=str(repo))
    assert (code, data["error"]) == (422, "No checkable claims found in the report.")


@pytest.mark.parametrize("value", ["01.01.2026 09:30", "2026-13-01 09:30", "2026-01-01", "yesterday"])
def test_bad_session_start_format(client, repo, value):
    code, data = post(client, report="Changed a.py", repo_path=str(repo), session_start=value)
    assert (code, data["field"]) == (400, "session")
    assert "YYYY-MM-DD HH:MM" in data["error"]


@pytest.mark.parametrize("value", ["2026-01-01 09:30", "2026-01-01T09:30"])
def test_good_session_start_shows_without_t(client, repo, monkeypatch, value):
    monkeypatch.setattr(verifier, "ask_gemini", lambda r, c: [
        verifier.Claim(claim="Changed a.py", verdict="unverifiable", explanation="x",
                       evidence="", files=[], scope_claim=False)])
    code, data = post(client, report="Changed a.py", repo_path=str(repo), session_start=value)
    assert code == 200
    assert data["mode"] == "all changes since 2026-01-01 09:30"


def test_unknown_preset(client, repo):
    code, data = post(client, report="Changed a.py", repo_path=str(repo), session="last-week")
    assert (code, data["field"]) == (400, "session")


@pytest.mark.parametrize("preset, expected", [
    ("1h", "2026-03-02 13:15"),
    ("3h", "2026-03-02 11:15"),
    ("today", "2026-03-02 00:00"),
    ("yesterday", "2026-03-01 00:00"),
])
def test_preset_start_times(preset, expected):
    from datetime import datetime
    from app import preset_start
    assert preset_start(preset, datetime(2026, 3, 2, 14, 15, 30)) == expected


def fake_claims(r, c):
    return [verifier.Claim(claim="Changed a.py", verdict="unverifiable", explanation="x",
                           evidence="", files=[], scope_claim=False)]


def test_preset_label_in_mode(client, repo, monkeypatch):
    monkeypatch.setattr(verifier, "ask_gemini", fake_claims)
    code, data = post(client, report="Changed a.py", repo_path=str(repo), session="today")
    assert code == 200 and data["mode"].endswith("(today)")


def test_auto_is_default(client, repo, monkeypatch):
    monkeypatch.setattr(verifier, "ask_gemini", fake_claims)
    code, data = post(client, report="Changed a.py", repo_path=str(repo))
    assert data["mode"] == "uncommitted changes vs last commit"
