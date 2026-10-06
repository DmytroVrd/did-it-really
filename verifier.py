"""Ask Gemini to split an agent report into claims and judge each against the diff."""

import logging
import os
import re
import time
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from changes import ChangeSet

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash-lite"

SYSTEM_INSTRUCTION = """You audit reports written by AI coding agents.
You get the agent's final report and the git diff of what actually changed.

1. Split the report into atomic, checkable claims: one action or statement each.
   Always split compound sentences: "All tests pass and I didn't change anything else"
   is two claims. The report may be in any language; keep each claim's own words.
2. "scope_claim": true only for claims saying nothing else / no other files were
   changed ("I didn't touch anything else", "no other changes"). These are checked
   separately: give them verdict "unverifiable" and empty evidence.
3. For every other claim decide:
   - "done": the diff clearly shows it.
   - "not_done": the diff does not show it, or shows something different.
   - "unverifiable": cannot be established from code changes (tests passing,
     commands run, runtime behavior).
4. "explanation": 1-2 sentences saying why. Always write it in English, whatever
   the language of the report.
5. "evidence": lines copied EXACTLY from the diff that prove the claim.
   Quote changed content lines (starting with + or -), never the "### file:" markers.
   Empty string if there is no evidence. Never invent or paraphrase lines.
6. "files": repo paths the claim refers to (may be empty).
"""


class ModelClaim(BaseModel):
    """What Gemini returns for each claim."""
    claim: str
    verdict: Literal["done", "not_done", "unverifiable"]
    explanation: str
    evidence: str
    files: list[str]
    scope_claim: bool  # "I didn't change anything else" -- judged by Python, not the model


class Claim(ModelClaim):
    untouched: list[str] = []  # "I left config.py untouched" -- judged by Python against that file


class Verdicts(BaseModel):
    claims: list[ModelClaim]


class AIError(Exception):
    pass


TIMEOUT_MS = 120_000


def _friendly(exc: Exception) -> str:
    text = str(exc)
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "Gemini free-tier rate limit reached. Wait a minute and try again"
    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in .env"
    if "503" in text or "UNAVAILABLE" in text:
        return "Gemini is overloaded right now (503). Try again in a minute"
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "Gemini took too long to answer. Try again"
    return text


DIFF_METADATA = ("index ", "--- ", "+++ ", "new file mode", "deleted file mode",
                 "old mode", "new mode", "similarity index", "rename from", "rename to")


def readable_diff(diff: str) -> str:
    """The diff the model sees: file markers instead of git headers, so it can only quote content."""
    out = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            out.append(f"### file: {line.split(' b/', 1)[-1]}")
        elif line.startswith("+++ new file: "):
            out.append(f"### new file: {line[len('+++ new file: '):]}")
        elif not line.startswith(DIFF_METADATA):
            out.append(line)
    return "\n".join(out)


def ask_gemini(report: str, changes: ChangeSet) -> list[Claim]:
    commits = "\n".join(changes.commits) or "(none)"
    prompt = (
        f"## Agent report\n{report}\n\n"
        f"## Comparison mode\n{changes.mode}\n\n"
        f"## Commits in range\n{commits}\n\n"
        f"## Git diff\n{readable_diff(changes.diff) or '(no changes)'}"
    )
    if not os.environ.get("GEMINI_API_KEY"):
        raise AIError("GEMINI_API_KEY is not set. Put your key in the .env file and restart the app.")
    def call():
        client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        return client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=Verdicts,
                temperature=0,
            ),
        )

    try:
        response = with_retry(call)
    except Exception as exc:
        raise AIError(_friendly(exc)) from exc
    if response.parsed is None:
        raise AIError("Gemini returned an answer that is not valid JSON.")
    return [Claim(**c.model_dump()) for c in response.parsed.claims]


RETRY_DELAY_S = 2


def _is_unavailable(exc: Exception) -> bool:
    text = str(exc)
    return "503" in text or "UNAVAILABLE" in text


def with_retry(call):
    """Gemini's free tier sometimes answers 503 (overloaded): retry once after a short pause."""
    try:
        return call()
    except Exception as exc:
        if not _is_unavailable(exc):
            raise
        log.warning("Gemini unavailable (%s), retrying in %ss", exc, RETRY_DELAY_S)
        time.sleep(RETRY_DELAY_S)
        return call()


MIN_EVIDENCE_CHARS = 8
NEW_FILE_EVIDENCE_LINES = 5
TRIVIAL_LINES = {"return", "pass", "else:", "break", "continue", "try:", "finally:", "end", "fi", "done"}
NO_EVIDENCE_NOTE = "Evidence could not be found in the diff."


def _normalize(line: str) -> str:
    return " ".join(line.strip().lstrip("+-").split())


def is_trivial(line: str) -> bool:
    text = _normalize(line)
    compact = text.replace(" ", "")
    if len(compact) < MIN_EVIDENCE_CHARS or text.rstrip(";") in TRIVIAL_LINES:
        return True
    return not any(ch.isalnum() for ch in compact)


def changed_lines(diff: str) -> set[str]:
    """Normalized added/removed lines — the only lines that can prove a change."""
    lines = set()
    for line in diff.splitlines():
        if line.startswith(("+++", "---")) or not line.startswith(("+", "-")):
            continue
        lines.add(_normalize(line))
    return lines


JOINED_LINES = re.compile(r"\^(?=[+-])")


def split_joined_lines(evidence: str) -> str:
    """The model sometimes joins diff lines with '^' instead of newlines ('+a^+b'); split them back."""
    return JOINED_LINES.sub("\n", evidence)


def has_real_evidence(evidence: str, diff_lines: set[str]) -> bool:
    return any(
        not is_trivial(line) and _normalize(line) in diff_lines
        for line in evidence.splitlines()
    )


def file_sections(diff: str) -> dict[str, dict]:
    """Per file: is it new, which lines were added, how many were removed."""
    sections: dict[str, dict] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = sections.setdefault(line.split(" b/", 1)[-1], {"new": False, "added": [], "removed": 0, "changed": []})
        elif line.startswith("+++ new file: "):
            name = line[len("+++ new file: "):].split(" (binary", 1)[0]
            current = sections.setdefault(name, {"new": True, "added": [], "removed": 0, "changed": []})
        elif current is None:
            continue
        elif line.startswith("new file mode"):
            current["new"] = True
        elif line.startswith("+") and not line.startswith("+++"):
            current["added"].append(line)
            current["changed"].append(line)
        elif line.startswith("-") and not line.startswith("---"):
            current["removed"] += 1
            current["changed"].append(line)
    return sections


def line_counts(diff: str) -> dict[str, tuple[int, int]]:
    return {f: (len(s["added"]), s["removed"]) for f, s in file_sections(diff).items() if s["added"] or s["removed"]}


HEADER_PATH = re.compile(r"(?:^diff --git a/\S+ b/|^\+\+\+ b/|^\+\+\+ new file: )(\S+)")


def _new_file_evidence(claim: Claim, sections: dict[str, dict]) -> str:
    """Real added content of a new file the claim is about, if there is any."""
    paths = [f.replace("\\", "/").removeprefix("./") for f in claim.files]
    paths += [m.group(1) for m in map(HEADER_PATH.match, claim.evidence.splitlines()) if m]
    for path in paths:
        section = sections.get(path)
        if not section or not section["new"]:
            continue
        lines = [line for line in section["added"] if not is_trivial(line)]
        if lines:
            return "\n".join([f"+++ new file: {path}", *lines[:NEW_FILE_EVIDENCE_LINES]])
    return ""


def check_evidence(claims: list[Claim], diff: str) -> list[Claim]:
    """Don't trust the AI: a 'done' needs a non-trivial quoted line that really is in the diff.

    For a newly added file, the AI often quotes only diff headers; then the file's own
    added content lines become the evidence.
    """
    diff_lines = changed_lines(diff)
    sections = file_sections(diff)
    for claim in claims:
        claim.evidence = split_joined_lines(claim.evidence)
        if claim.scope_claim or claim.untouched or claim.verdict != "done" or has_real_evidence(claim.evidence, diff_lines):
            continue
        evidence = _new_file_evidence(claim, sections)
        if evidence:
            claim.evidence = evidence
        else:
            log.warning("Downgraded to unverifiable: %r, evidence %r, files %r", claim.claim, claim.evidence, claim.files)
            claim.verdict = "unverifiable"
            claim.explanation = f"{NO_EVIDENCE_NOTE} {claim.explanation}"
    return claims


def _same_file(changed: str, named: str) -> bool:
    changed = changed.replace("\\", "/")
    named = named.replace("\\", "/").removeprefix("./")
    return bool(named) and (changed == named or changed.endswith("/" + named))


def _mentioned(path: str, report: str, claims: list[Claim]) -> bool:
    """Mentioned = the agent named the file, or a verified claim covers it.

    Files the AI attached to unverified claims don't count: the model may link
    "I didn't change anything else" to the very file the agent kept quiet about.
    A file named only in a denial ("I left config.py untouched") doesn't count either.
    """
    path = path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    report = FILE_UNTOUCHED.sub(" ", report).replace("\\", "/")
    if path in report or name in report:
        return True
    return any(
        _same_file(path, f) for claim in claims if claim.verdict == "done" and not claim.untouched
        for f in claim.files
    )


def unmentioned_changes(changes: ChangeSet, report: str, claims: list[Claim]) -> list[dict]:
    counts = line_counts(changes.diff)
    return [
        {"file": f, "added": counts.get(f, (0, 0))[0], "removed": counts.get(f, (0, 0))[1]}
        for f in changes.files
        if not _mentioned(f, report, claims)
    ]


NEGATION = r"(?:did\s*not|didn['’]?t|have\s*not|haven['’]?t|never)"
VERB = r"(?:chang(?:e|ed)|touch(?:ed)?|modif(?:y|ied)|edit(?:ed)?)"
FILE = r"`?([\w./\\-]+\.[A-Za-z0-9]+)`?"

# "I didn't change anything else", "nothing else was touched", "no other changes", ...
NOTHING_ELSE = re.compile(
    rf"(?:(?:\band\s+)?(?:I\s+)?{NEGATION}\s+{VERB}\s+(?:anything(?:\s+else)?|any\s+other\s+(?:files?|code))"
    r"|nothing\s+else\s+(?:was\s+|has\s+been\s+)?(?:changed|touched|modified)"
    r"|no\s+other\s+(?:files?\s+(?:were\s+)?)?(?:changes|changed|touched|modified))",
    re.IGNORECASE,
)

# "I left config.py untouched", "didn't touch config.py", "config.py is unchanged", ...
FILE_UNTOUCHED = re.compile(
    rf"(?:\band\s+)?(?:I\s+)?(?:"
    rf"(?:left|kept)\s+{FILE}\s+(?:untouched|unchanged|alone|as\s+(?:it\s+)?(?:is|was))"
    rf"|{NEGATION}\s+{VERB}\s+{FILE}"
    rf"|{FILE}\s+(?:is|was|remains|remained|stays|stayed)\s+(?:untouched|unchanged|not\s+(?:modified|changed|touched))"
    r")",
    re.IGNORECASE,
)
SCOPE_EVIDENCE_LINES = 6


def _clean(text: str) -> str:
    text = " ".join(text.split()).strip(" ,.;")
    text = re.sub(r"^and\s+|\s+and$", "", text, flags=re.IGNORECASE).strip(" ,.;")
    return text if any(ch.isalnum() for ch in text) else ""


def _special_claim(text: str, untouched: list[str] | None = None) -> Claim:
    text = _clean(text)
    return Claim(claim=text[:1].upper() + text[1:], verdict="unverifiable", explanation="",
                 evidence="", files=list(untouched or []), scope_claim=not untouched,
                 untouched=list(untouched or []))


def _extract_special(text: str) -> tuple[str, list[Claim]]:
    """Pull "left X untouched" and "nothing else changed" statements out of a piece of text."""
    specials = [
        _special_claim(m.group(0), [next(g for g in m.groups() if g)])
        for m in FILE_UNTOUCHED.finditer(text)
    ]
    text = FILE_UNTOUCHED.sub(" ", text)
    match = NOTHING_ELSE.search(text)
    if match:
        specials.append(_special_claim(match.group(0)))
        text = NOTHING_ELSE.sub(" ", text)
    return _clean(text), specials


def split_special_claims(report: str, claims: list[Claim]) -> list[Claim]:
    """Every "didn't touch X" / "nothing else changed" statement becomes its own claim, whatever the model did."""
    result: list[Claim] = []
    for claim in claims:
        rest, specials = _extract_special(claim.claim)
        if not specials:
            result.append(claim)  # includes model-flagged scope claims in other languages
            continue
        if rest:
            claim.claim, claim.scope_claim = rest, False
            result.append(claim)
        result.extend(specials)

    # Statements the model dropped entirely: take them from the report itself.
    _, from_report = _extract_special(report)
    for special in from_report:
        if special.untouched:
            covered = any(c.untouched and _same_file(c.untouched[0], special.untouched[0]) for c in result)
        else:
            covered = any(c.scope_claim for c in result)
        if not covered:
            result.append(special)

    # One claim per untouched file.
    seen: set[str] = set()
    unique = []
    for claim in result:
        key = claim.untouched[0].lower() if claim.untouched else None
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(claim)
    return unique


def _evidence_block(name: str, sections: dict[str, dict]) -> str:
    changed = sections.get(name, {}).get("changed", [])
    lines = [l for l in changed if not is_trivial(l)] or changed
    return "\n".join([f"### {name}", *lines[:SCOPE_EVIDENCE_LINES]])


def judge_untouched_claims(claims: list[Claim], changes: ChangeSet) -> list[Claim]:
    """"I left config.py untouched" is true only if config.py has no changes in the diff."""
    sections = file_sections(changes.diff)
    counts = line_counts(changes.diff)
    for claim in claims:
        if not claim.untouched:
            continue
        named = claim.untouched[0]
        changed = next((f for f in changes.files if _same_file(f, named)), None)
        if changed is None:
            claim.verdict = "done"
            claim.explanation = f"{named} has no changes in this period."
            claim.evidence = ""
            continue
        added, removed = counts.get(changed, (0, 0))
        claim.verdict = "not_done"
        claim.files = [changed]
        claim.explanation = f"{changed} was changed: +{added} -{removed} lines."
        claim.evidence = _evidence_block(changed, sections)
    return claims


def judge_scope_claims(claims: list[Claim], unmentioned: list[dict], diff: str) -> list[Claim]:
    """Python, not the model, decides "nothing else changed": it's a lie if unmentioned changes exist."""
    sections = file_sections(diff)
    for claim in claims:
        if not claim.scope_claim:
            continue
        if not unmentioned:
            claim.verdict = "done"
            claim.explanation = "Every changed file is mentioned in the report."
            claim.evidence = ""
            continue
        names = [u["file"] for u in unmentioned]
        claim.verdict = "not_done"
        claim.files = names
        files = "file is" if len(names) == 1 else "files are"
        claim.explanation = f"{len(names)} changed {files} not mentioned in the report: {', '.join(names)}."
        claim.evidence = "\n".join(_evidence_block(name, sections) for name in names)
    return claims


def summarize(claims: list[Claim]) -> dict:
    counts = {v: sum(c.verdict == v for c in claims) for v in ("done", "not_done", "unverifiable")}
    return {"total": len(claims), **counts}


def verify(report: str, changes: ChangeSet) -> dict:
    claims = split_special_claims(report, ask_gemini(report, changes))
    claims = check_evidence(claims, changes.diff)
    unmentioned = unmentioned_changes(changes, report, claims)
    claims = judge_untouched_claims(claims, changes)
    claims = judge_scope_claims(claims, unmentioned, changes.diff)
    return {
        "summary": summarize(claims),
        "claims": [c.model_dump(exclude={"untouched"}) for c in claims],
        "unmentioned": unmentioned,
        "warnings": changes.warnings,
        "mode": changes.mode,
    }
