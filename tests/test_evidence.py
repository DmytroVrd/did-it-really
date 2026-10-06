import verifier
from changes import ChangeSet
from verifier import Claim, check_evidence, is_trivial, unmentioned_changes, verify

DIFF = """diff --git a/calc.py b/calc.py
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,6 @@
 def add(a, b):
     return a + b
+
+def multiply(a, b):
+    return a * b
+}
-OLD_CONSTANT = 42
+++ new file: extra.py
+print("hi")
"""


def claim(verdict="done", evidence="", files=None, text="Added multiply to calc.py", scope=False):
    return Claim(claim=text, verdict=verdict, explanation="why", evidence=evidence,
                 files=files or [], scope_claim=scope)


def test_real_line_stays_done():
    [c] = check_evidence([claim(evidence="+def multiply(a, b):")], DIFF)
    assert c.verdict == "done"


def test_whitespace_differences_are_ignored():
    [c] = check_evidence([claim(evidence="def   multiply(a,  b):  ")], DIFF)
    assert c.verdict == "done"


def test_invented_evidence_is_downgraded():
    [c] = check_evidence([claim(evidence="+def divide(a, b):")], DIFF)
    assert c.verdict == "unverifiable"
    assert c.explanation.startswith(verifier.NO_EVIDENCE_NOTE)


def test_empty_evidence_is_downgraded():
    [c] = check_evidence([claim(evidence="")], DIFF)
    assert c.verdict == "unverifiable"


def test_trivial_only_evidence_is_downgraded():
    [c] = check_evidence([claim(evidence="+}\n+    return")], DIFF)
    assert c.verdict == "unverifiable"


def test_unchanged_context_line_is_not_evidence():
    [c] = check_evidence([claim(evidence="def add(a, b):")], DIFF)
    assert c.verdict == "unverifiable"


def test_removed_line_counts_as_evidence():
    [c] = check_evidence([claim(evidence="-OLD_CONSTANT = 42", text="Removed OLD_CONSTANT")], DIFF)
    assert c.verdict == "done"


NEW_FILE_DIFF = """diff --git a/demo/make_demo_repo.py b/demo/make_demo_repo.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/demo/make_demo_repo.py
@@ -0,0 +1,4 @@
+import subprocess
+
+def main():
+    subprocess.run(["git", "init"])
diff --git a/empty.py b/empty.py
new file mode 100644
--- /dev/null
+++ b/empty.py
@@ -0,0 +1 @@
+}
diff --git a/calc.py b/calc.py
--- a/calc.py
+++ b/calc.py
@@ -1 +1 @@
-x = 1
+x = 2
+++ new file: notes.txt
+Remember to update the changelog
"""

HEADERS_ONLY = "diff --git a/demo/make_demo_repo.py b/demo/make_demo_repo.py\nnew file mode 100644\n+++ b/demo/make_demo_repo.py"


def test_new_file_with_header_only_evidence_uses_real_content():
    [c] = check_evidence([claim(evidence=HEADERS_ONLY, files=[], text="Added demo/make_demo_repo.py")], NEW_FILE_DIFF)
    assert c.verdict == "done"
    assert "+def main():" in c.evidence
    assert "+import subprocess" in c.evidence
    assert "new file mode" not in c.evidence


def test_new_file_found_via_claim_files():
    [c] = check_evidence([claim(evidence="", files=["./demo/make_demo_repo.py"])], NEW_FILE_DIFF)
    assert c.verdict == "done"


def test_untracked_new_file_counts():
    [c] = check_evidence([claim(evidence="+++ new file: notes.txt", files=["notes.txt"])], NEW_FILE_DIFF)
    assert c.verdict == "done"
    assert "+Remember to update the changelog" in c.evidence


def test_new_file_with_only_trivial_content_is_downgraded():
    [c] = check_evidence([claim(evidence="+++ b/empty.py", files=["empty.py"])], NEW_FILE_DIFF)
    assert c.verdict == "unverifiable"


def test_headers_of_modified_file_are_not_evidence():
    [c] = check_evidence([claim(evidence="diff --git a/calc.py b/calc.py\n+++ b/calc.py", files=["calc.py"])], NEW_FILE_DIFF)
    assert c.verdict == "unverifiable"


def test_line_counts_for_new_files():
    counts = verifier.line_counts(NEW_FILE_DIFF)
    assert counts["demo/make_demo_repo.py"] == (4, 0)
    assert counts["calc.py"] == (1, 1)
    assert counts["notes.txt"] == (1, 0)


def test_other_verdicts_untouched():
    claims = check_evidence([claim("not_done"), claim("unverifiable")], DIFF)
    assert [c.verdict for c in claims] == ["not_done", "unverifiable"]


def test_is_trivial():
    assert is_trivial("+}")
    assert is_trivial("  return")
    assert is_trivial("+  ) ] ;")
    assert not is_trivial("+    return a * b")


def test_unmentioned_file_detected():
    changes = ChangeSet(diff=DIFF, files=["calc.py", "extra.py"], commits=[], mode="m")
    result = unmentioned_changes(changes, "Added multiply to calc.py", [claim(files=["calc.py"])])
    assert result == [{"file": "extra.py", "added": 1, "removed": 0}]


def test_file_named_in_report_is_mentioned():
    changes = ChangeSet(diff=DIFF, files=["calc.py", "extra.py"], commits=[], mode="m")
    assert unmentioned_changes(changes, "Edited calc.py and extra.py", []) == []


def test_verified_claim_files_count_as_mentioned():
    changes = ChangeSet(diff=DIFF, files=["calc.py"], commits=[], mode="m")
    assert unmentioned_changes(changes, "Added multiply", [claim(files=["calc.py"])]) == []


def test_ai_linking_file_to_failed_claim_does_not_hide_it():
    # "I didn't change anything else" -> not_done, AI attaches the quietly changed file.
    changes = ChangeSet(diff=DIFF, files=["extra.py"], commits=[], mode="m")
    lie = claim("not_done", files=["extra.py"], text="I didn't change anything else")
    result = unmentioned_changes(changes, "I didn't change anything else", [lie])
    assert result == [{"file": "extra.py", "added": 1, "removed": 0}]


def test_summary_counts_after_downgrade(monkeypatch):
    fake = [claim(evidence="+def multiply(a, b):", files=["calc.py"]), claim(evidence="+}"), claim("not_done")]
    monkeypatch.setattr(verifier, "ask_gemini", lambda report, changes: fake)
    changes = ChangeSet(diff=DIFF, files=["calc.py", "extra.py"], commits=[], mode="m")
    result = verify("report", changes)
    assert result["summary"] == {"total": 3, "done": 1, "not_done": 1, "unverifiable": 1}
    assert result["unmentioned"] == [{"file": "extra.py", "added": 1, "removed": 0}]


def test_readable_diff_hides_git_headers():
    text = verifier.readable_diff(NEW_FILE_DIFF)
    assert "### file: demo/make_demo_repo.py" in text
    assert "### new file: notes.txt" in text
    assert "+def main():" in text and "-x = 1" in text
    for header in ("diff --git", "new file mode", "index ", "--- /dev/null", "+++ b/"):
        assert header not in text
