"""Create a SAMPLE repository where an "agent" did part of the work and reported more.

Usage:  python demo/make_demo_repo.py [target_folder]
Prints the fake agent report and the repo path to paste into the app; pick "Last hour".
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TASKS_BEFORE = '''TASKS = []


def add_task(title):
    TASKS.append({"title": title, "done": False})
    return TASKS[-1]
'''

TASKS_AFTER = TASKS_BEFORE + '''

def complete_task(index):
    TASKS[index]["done"] = True
    return TASKS[index]
'''

SETTINGS_BEFORE = 'DEBUG = False\nMAX_TASKS = 100\n'
SETTINGS_AFTER = 'DEBUG = True\nMAX_TASKS = 100000\n'

REPORT = """Done! Here's what I did:
- Added complete_task(index) to tasks.py to mark a task as done
- Added validation to add_task so empty titles raise ValueError
- Updated the README with usage examples
- All tests pass and I didn't change anything else."""


def git(repo, *args, date=None):
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def write(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8", newline="\n")


def _force_remove(func, path, _):
    os.chmod(path, stat.S_IWRITE)  # git marks objects read-only on Windows
    func(path)


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "did-it-really-demo"
    if target.exists():
        shutil.rmtree(target, onerror=_force_remove)
    target.mkdir(parents=True)

    git(target, "init", "-q")
    git(target, "config", "user.email", "demo@example.com")
    git(target, "config", "user.name", "Demo")
    git(target, "config", "core.autocrlf", "false")

    write(target, "tasks.py", TASKS_BEFORE)
    write(target, "settings.py", SETTINGS_BEFORE)
    write(target, "README.md", "# Tiny tasks\n")
    git(target, "add", ".")
    now = datetime.now()

    def minutes_ago(minutes):
        return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")

    git(target, "commit", "-q", "-m", "Initial tasks module", date=minutes_ago(2 * 24 * 60))

    # The "agent session": two commits within the last hour.
    write(target, "tasks.py", TASKS_AFTER)
    git(target, "commit", "-qam", "Add complete_task", date=minutes_ago(40))
    write(target, "settings.py", SETTINGS_AFTER)  # changed quietly, never mentioned
    git(target, "commit", "-qam", "Tweak settings", date=minutes_ago(15))

    print("SAMPLE DATA — demo repository created.\n")
    print(f"Repository path:\n  {target}\n")
    print("Agent session:\n  Last hour\n")
    print("Agent report (paste into the app):\n")
    print(REPORT)


if __name__ == "__main__":
    main()
