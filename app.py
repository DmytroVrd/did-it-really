"""Did it really? — local web app that checks an AI agent's report against git."""

from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from changes import GitError, collect_changes, is_git_repo
from verifier import AIError, verify

load_dotenv()
app = Flask(__name__)


SESSION_FORMAT = "%Y-%m-%d %H:%M"


def parse_session_start(value: str) -> str | None:
    """'2026-01-01 09:30' (or with a T) -> '2026-01-01 09:30'; None if invalid."""
    try:
        return datetime.strptime(value.replace("T", " ", 1), SESSION_FORMAT).strftime(SESSION_FORMAT)
    except ValueError:
        return None


# Session presets shown as buttons. "auto" = no start time: uncommitted vs last commit,
# or last commit vs previous one.
SESSION_PRESETS = {
    "1h": "last hour",
    "3h": "last 3 hours",
    "today": "today",
    "yesterday": "since yesterday",
}


def preset_start(preset: str, now: datetime) -> str:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = {
        "1h": now - timedelta(hours=1),
        "3h": now - timedelta(hours=3),
        "today": midnight,
        "yesterday": midnight - timedelta(days=1),
    }[preset]
    return start.strftime(SESSION_FORMAT)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/check")
def check():
    data = request.get_json(silent=True) or {}
    report = (data.get("report") or "").strip()
    repo_path = (data.get("repo_path") or "").strip().strip('"')
    session = (data.get("session") or "auto").strip()
    # Exact start time: API only (scripts, tests); the page uses presets.
    session_start = (data.get("session_start") or "").strip() or None

    if not report:
        return jsonify(error="Paste the agent's report first.", field="report"), 400
    if not repo_path:
        return jsonify(error="Enter the path to the project folder.", field="repo_path"), 400
    if not Path(repo_path).is_dir():
        return jsonify(error="This folder does not exist.", field="repo_path"), 400
    if not is_git_repo(Path(repo_path)):
        return jsonify(error="There is no git repository in this folder.", field="repo_path"), 400
    if session_start:
        session_start = parse_session_start(session_start)
        if not session_start:
            return jsonify(error="Use the format YYYY-MM-DD HH:MM, e.g. 2026-01-01 09:30.",
                           field="session"), 400
    elif session != "auto":
        if session not in SESSION_PRESETS:
            return jsonify(error="Unknown session preset.", field="session"), 400
        session_start = preset_start(session, datetime.now())

    try:
        changes = collect_changes(repo_path, session_start)
        if session in SESSION_PRESETS and not data.get("session_start"):
            changes.mode += f" ({SESSION_PRESETS[session]})"
        result = verify(report, changes)
    except GitError as exc:
        return jsonify(error=f"git failed: {exc}", field="repo_path"), 400
    except AIError as exc:
        return jsonify(error=f"AI check failed: {exc}."), 502

    if not result["claims"]:
        return jsonify(error="No checkable claims found in the report.", field="report"), 422
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
