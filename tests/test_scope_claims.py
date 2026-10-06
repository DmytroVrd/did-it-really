""""I didn't change anything else" is judged by Python, deterministically."""

import pytest

import verifier
from changes import ChangeSet
from verifier import NOTHING_ELSE, Claim, split_special_claims, verify

DIFF = """diff --git a/tasks.py b/tasks.py
--- a/tasks.py
+++ b/tasks.py
@@ -5,0 +6,4 @@
+def complete_task(index):
+    TASKS[index]["done"] = True
+    return TASKS[index]
diff --git a/settings.py b/settings.py
--- a/settings.py
+++ b/settings.py
@@ -1,2 +1,2 @@
-DEBUG = False
-MAX_TASKS = 100
+DEBUG = True
+MAX_TASKS = 100000
"""

REPORT = """Done!
- Added complete_task(index) to tasks.py
- All tests pass and I didn't change anything else."""


def claim(text, verdict="unverifiable", evidence="", files=None, scope=False):
    return Claim(claim=text, verdict=verdict, explanation="why", evidence=evidence,
                 files=files or [], scope_claim=scope)


DONE_TASKS = claim("Added complete_task(index) to tasks.py", "done", "+def complete_task(index):", ["tasks.py"])


def run(monkeypatch, model_claims, files=("tasks.py", "settings.py"), report=REPORT):
    monkeypatch.setattr(verifier, "ask_gemini", lambda r, c: model_claims)
    return verify(report, ChangeSet(diff=DIFF, files=list(files), commits=[], mode="m"))


@pytest.mark.parametrize("text", [
    "I didn't change anything else",
    "I did not touch anything else",
    "and I haven't modified any other files",
    "Nothing else was changed",
    "No other files were touched",
    "no other changes",
])
def test_nothing_else_phrases_are_recognized(text):
    assert NOTHING_ELSE.search(text)


@pytest.mark.parametrize("text", ["Changed settings.py", "All tests pass", "Updated the README"])
def test_ordinary_claims_are_not_scope_claims(text):
    assert not NOTHING_ELSE.search(text)


def test_merged_claim_is_split_and_lie_caught(monkeypatch):
    # The model merged both statements into one unverifiable claim (what happened in the demo).
    merged = claim("All tests pass and I didn't change anything else.")
    result = run(monkeypatch, [DONE_TASKS, merged])
    texts = [(c["claim"], c["verdict"]) for c in result["claims"]]
    assert texts == [
        ("Added complete_task(index) to tasks.py", "done"),
        ("All tests pass", "unverifiable"),
        ("I didn't change anything else", "not_done"),
    ]
    lie = result["claims"][-1]
    assert "settings.py" in lie["explanation"]
    assert "### settings.py" in lie["evidence"] and "+DEBUG = True" in lie["evidence"]
    assert result["summary"] == {"total": 3, "done": 1, "not_done": 1, "unverifiable": 1}


def test_model_flagged_scope_claim_is_judged_by_python(monkeypatch):
    flagged = claim("I didn't change anything else", "done", scope=True)  # model wrongly says done
    result = run(monkeypatch, [DONE_TASKS, claim("All tests pass"), flagged])
    assert result["claims"][-1]["verdict"] == "not_done"


def test_scope_claim_missing_from_model_is_added_from_report(monkeypatch):
    result = run(monkeypatch, [DONE_TASKS, claim("All tests pass")])
    assert result["claims"][-1]["claim"] == "I didn't change anything else"
    assert result["claims"][-1]["verdict"] == "not_done"


def test_scope_claim_true_when_every_change_is_mentioned(monkeypatch):
    result = run(monkeypatch, [DONE_TASKS, claim("All tests pass")], files=["tasks.py"])
    scope = result["claims"][-1]
    assert scope["verdict"] == "done"
    assert scope["explanation"] == "Every changed file is mentioned in the report."


def test_no_scope_claim_when_report_does_not_say_it(monkeypatch):
    result = run(monkeypatch, [DONE_TASKS], report="Added complete_task(index) to tasks.py")
    assert not any(c["scope_claim"] for c in result["claims"])


def test_only_one_scope_claim_when_model_already_split(monkeypatch):
    claims = split_special_claims(REPORT, [DONE_TASKS, claim("All tests pass"),
                                         claim("I didn't change anything else", scope=True)])
    assert sum(c.scope_claim for c in claims) == 1
