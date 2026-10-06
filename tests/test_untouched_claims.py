""""I left config.py untouched" is checked against config.py itself."""

import pytest

import verifier
from changes import ChangeSet
from verifier import FILE_UNTOUCHED, NOTHING_ELSE, Claim, split_special_claims, verify

# The bug report: the agent quietly changed config.py and also left an untracked note.
DIFF = """diff --git a/shop.py b/shop.py
--- a/shop.py
+++ b/shop.py
@@ -4,0 +5,3 @@
+def total_with_tax(items, rate=0.2):
+    return round(total(items) * (1 + rate), 2)
diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -1,2 +1,2 @@
 CURRENCY = "UAH"
-DISCOUNT = 0
+DISCOUNT = 50
+++ new file: notes_todo.txt
+remember to ask about refunds policy before release
"""
FILES = ["shop.py", "config.py", "notes_todo.txt"]
REPORT = "Done!\n- Added total_with_tax() to shop.py\n- I left config.py untouched."


def claim(text, verdict="unverifiable", evidence="", files=None, scope=False):
    return Claim(claim=text, verdict=verdict, explanation="why", evidence=evidence,
                 files=files or [], scope_claim=scope)


SHOP = claim("Added total_with_tax() to shop.py", "done", "+def total_with_tax(items, rate=0.2):", ["shop.py"])


def run(monkeypatch, model_claims, report=REPORT, files=FILES):
    monkeypatch.setattr(verifier, "ask_gemini", lambda r, c: model_claims)
    return verify(report, ChangeSet(diff=DIFF, files=list(files), commits=[], mode="m"))


@pytest.mark.parametrize("text, file", [
    ("I left config.py untouched", "config.py"),
    ("kept `src/config.py` unchanged", "src/config.py"),
    ("I didn't touch config.py", "config.py"),
    ("did not modify settings.json", "settings.json"),
    ("config.py is unchanged", "config.py"),
    ("config.py was not modified", "config.py"),
])
def test_file_denials_are_recognized(text, file):
    match = FILE_UNTOUCHED.search(text)
    assert match and next(g for g in match.groups() if g) == file


@pytest.mark.parametrize("text", ["I didn't change anything else", "Updated config.py", "Left a note in README"])
def test_not_file_denials(text):
    assert not FILE_UNTOUCHED.search(text)


def test_general_rule_ignores_file_denials():
    assert not NOTHING_ELSE.search("I left config.py untouched")
    assert not NOTHING_ELSE.search("I didn't touch config.py")


def test_bug_report_scenario(monkeypatch):
    # What Gemini returned: the denial flagged as a general "nothing else" claim.
    model = [SHOP, claim("I left config.py untouched.", scope=True)]
    result = run(monkeypatch, model)
    denial = result["claims"][-1]
    assert denial["claim"] == "I left config.py untouched"
    assert denial["verdict"] == "not_done"
    assert denial["explanation"] == "config.py was changed: +1 -1 lines."
    assert "### config.py" in denial["evidence"]
    assert "-DISCOUNT = 0" in denial["evidence"] and "+DISCOUNT = 50" in denial["evidence"]
    assert "notes_todo.txt" not in denial["evidence"]
    assert not denial["scope_claim"]


def test_file_named_only_in_denial_is_unmentioned(monkeypatch):
    result = run(monkeypatch, [SHOP, claim("I left config.py untouched")])
    assert [u["file"] for u in result["unmentioned"]] == ["config.py", "notes_todo.txt"]


def test_untouched_file_really_untouched(monkeypatch):
    result = run(monkeypatch, [SHOP, claim("I didn't touch README.md")],
                 report="Added total_with_tax() to shop.py. I didn't touch README.md.")
    denial = result["claims"][-1]
    assert denial["verdict"] == "done"
    assert denial["explanation"] == "README.md has no changes in this period."


def test_denial_dropped_by_model_is_added_from_report(monkeypatch):
    result = run(monkeypatch, [SHOP])
    assert result["claims"][-1]["claim"] == "I left config.py untouched"
    assert result["claims"][-1]["verdict"] == "not_done"


def test_denial_merged_into_other_claim_is_split(monkeypatch):
    merged = claim("Added total_with_tax() to shop.py and left config.py untouched", "done",
                   "+def total_with_tax(items, rate=0.2):", ["shop.py"])
    result = run(monkeypatch, [merged], report="Added total_with_tax() to shop.py and left config.py untouched.")
    assert [(c["claim"], c["verdict"]) for c in result["claims"]] == [
        ("Added total_with_tax() to shop.py", "done"),
        ("Left config.py untouched", "not_done"),
    ]


def test_denial_and_nothing_else_in_one_sentence(monkeypatch):
    report = "Added total_with_tax() to shop.py. I left config.py untouched and didn't change anything else."
    result = run(monkeypatch, [SHOP, claim("I left config.py untouched and didn't change anything else")], report=report)
    verdicts = {c["claim"]: c["verdict"] for c in result["claims"]}
    assert verdicts["I left config.py untouched"] == "not_done"
    assert verdicts["Didn't change anything else"] == "not_done"


def test_one_claim_per_untouched_file():
    claims = split_special_claims(REPORT, [SHOP, claim("I left config.py untouched"),
                                           claim("config.py is unchanged")])
    assert sum(bool(c.untouched) for c in claims) == 1


def test_retry_once_on_503(monkeypatch):
    monkeypatch.setattr(verifier, "RETRY_DELAY_S", 0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise Exception("503 UNAVAILABLE. The model is overloaded.")
        return "ok"

    assert verifier.with_retry(flaky) == "ok"
    assert len(calls) == 2


def test_no_retry_on_other_errors(monkeypatch):
    monkeypatch.setattr(verifier, "RETRY_DELAY_S", 0)
    calls = []

    def broken():
        calls.append(1)
        raise Exception("400 INVALID_ARGUMENT")

    with pytest.raises(Exception):
        verifier.with_retry(broken)
    assert len(calls) == 1


def test_second_503_gives_friendly_message():
    assert "overloaded" in verifier._friendly(Exception("503 UNAVAILABLE"))
