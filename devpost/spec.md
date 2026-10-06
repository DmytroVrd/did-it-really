---
doc: spec
status: approved
---

# Did it really? — Technical Spec

## How This Works, In Plain Language
Did it really? is a small Python program (a **Flask** server) that runs on your laptop and serves one web page.

1. You paste the agent's final report and the path to your project folder, then press **Check**.
2. The server runs ordinary `git` commands in that folder to collect **what actually changed** — the diff (uncommitted changes, plus commits made during the agent's session).
3. The server sends the report and the diff to **Gemini** in a single request and asks it to split the report into claims and judge each one as ✅ / ❌ / ⚠️, quoting diff lines as evidence.
4. **We don't trust Gemini blindly either.** Python checks that every quoted evidence snippet literally exists in the real diff. If a ✅ has no real evidence, it is downgraded to ⚠️ with a note.
5. Python also lists **changes the agent didn't mention**: files changed in the diff that no claim refers to.
6. The page draws the receipt: summary on top, one row per claim with verdict, explanation and diff snippet, then the unmentioned changes.

Nothing is saved: no database, no accounts. Reload the page and it's gone.
Why this shape: Python is Dmytro's language, Flask is a few lines, one AI call keeps us inside the free tier, and the git part is plain commands anyone can re-run by hand.

## The Core Journey Through the System
PRD ref: `prd.md > The Core Journey`.

```
Browser (index.html + app.js)
   │  POST /api/check {report, repo_path, session_start?}
   ▼
Flask (app.py) ── validate input ──► error JSON → message next to field
   │
   ├─► changes.py: git status / log / diff in repo_path → ChangeSet (diff, changed files, commits, warnings)
   │
   ├─► verifier.py: one Gemini call (report + diff) → claims[] as JSON
   │        ├─► evidence check: a non-trivial quoted line must exist in diff; else ✅ → ⚠️
   │        └─► unmentioned changes: changed files no claim refers to
   ▼
JSON {summary, claims[], unmentioned[], warnings[]} → app.js renders the receipt
```

1. User opens `http://localhost:5000` → Flask serves `templates/index.html`.
2. Fills the form, presses **Check** → `app.js` disables the button, shows "Checking…", sends `POST /api/check`.
3. `app.py` validates input (see `Important Failure Modes`).
4. `changes.py` builds the ChangeSet (see `Choosing What Counts as "Changed"`).
5. `verifier.py` calls Gemini, gets structured JSON, runs the evidence check, computes the summary.
6. `app.js` renders summary + claim rows + "Changes the agent didn't mention". Button re-enabled.

## Stack
- **Python 3.11** (installed: 3.11.9) — Dmytro's language.
- **Flask 3.x** — tiny local web server. Docs: https://flask.palletsprojects.com/
- **google-genai** (Google Gen AI Python SDK) — Gemini calls with structured JSON output (`response_schema` with a Pydantic model). Docs: https://googleapis.github.io/python-genai/ · https://ai.google.dev/gemini-api/docs/structured-output
- **pydantic** — schema for Gemini's answer (comes with google-genai).
- **python-dotenv** — loads `GEMINI_API_KEY` from `.env`. Docs: https://pypi.org/project/python-dotenv/
- **git CLI** (installed: 2.53) via `subprocess` — no git library needed.
- **Frontend:** plain HTML + CSS + vanilla JS. No framework, no build step.
- **pytest** — tests for the git and evidence-check logic (no AI calls in tests).

Rationale: learner chose Python and accepted the Flask + plain page recommendation (tradeoff: hand-written UI, no component library — fine for one page). Learner chose Gemini free tier.
**Model:** `gemini-3.5-flash-lite` (verified in build: free tier 15 RPM / 500 requests/day / 250K TPM). Set via `GEMINI_MODEL` in `.env`.

## Where It Runs and How Someone Tries It
- Runs locally on Windows (also works on macOS/Linux). Needs Python 3.11+, git, a free Gemini API key from https://aistudio.google.com/apikey.
- Setup:
  ```
  pip install -r requirements.txt
  copy .env.example .env      # then put GEMINI_API_KEY=... inside
  python demo/make_demo_repo.py   # optional: creates the demo repo for the video
  python app.py
  ```
- Open **http://localhost:5000**.
- **Demo recording:** run `make_demo_repo.py`, paste the printed fake agent report and repo path, press Check, show the ❌ lighting up where the "agent" lied.
- **No deployment** (learner decision). Submission = demo video + public GitHub repo.
- **Public repository:** https://github.com/DmytroVrd/did-it-really
- **Demo video:** _to be added after recording_
- **Recording tip:** dark theme compresses on screen recordings — record at 125% browser zoom; demo uses the **Last hour** preset.

## Look and Feel
From `prd.md > Look and Feel`. Both themes were previewed in build; **Dmytro chose Terminal** and the Receipt theme was removed. Final review: terminal-window frame with ● ● ● and `did-it-really` title, green ▶ RUN CHECK, ✓ VERIFIED / ✗ NOT FOUND / ! UNVERIFIABLE badges before each claim, `==== 1 verified · 2 not found · 1 unverifiable ====` summary, orange-framed unmentioned block, **Dracula palette** (official accents; muted text `#b6b9cc` derived for contrast).
- ~~**Receipt:**~~ (not chosen) monospace font (e.g. `"JetBrains Mono", "Consolas", monospace`), off-white paper background (~`#faf8f3`) on a soft grey page, narrow centered column (~640px), dashed separators, rotated "stamp" labels VERIFIED (green) / NOT FOUND (red) / UNVERIFIABLE (amber).
- **Terminal test report (chosen):** dark background (~`#0d1117`), monospace, green `#3fb950` / red `#f85149` / amber `#d29922`, like pytest output.
- Both: verdict icons ✅ ❌ ⚠️; diff snippets in a monospace block with `+` lines green and `-` lines red; short, dry interface copy in English.

## Components

### Web Page (`templates/index.html`, `static/app.js`, `static/style.css`)
Form (report textarea, repo path input, agent-session preset buttons (Auto · Last hour · Last 3 hours · Today · Yesterday; `app.py > preset_start` turns them into a start time), **Check** button), loading state, error messages per field, receipt rendering, and the "Changes the agent didn't mention" block (hidden when empty).
PRD ref: `prd.md > Screens and Layout`, `prd.md > States and Boundaries`.

### Flask Server (`app.py`)
Routes: `GET /` → page; `POST /api/check` → JSON. Validates input, calls `changes.py` then `verifier.py`, returns result or `{error, field}`.

### Choosing What Counts as "Changed" (`changes.py`)
Implements `prd.md > What Counts as a Change (Comparing With Git)`.
- **All git calls** go through one helper: `subprocess.run([...], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")`. On Windows the default codec is cp1251; Cyrillic or emoji in diffs would otherwise crash. Untracked files are read the same way (`encoding="utf-8", errors="replace"`).
- Not a git repo (`git rev-parse --is-inside-work-tree` fails) → error.
- Folder is inside a larger repo (`git rev-parse --show-toplevel` differs) → run everything from the repo root and add warning "This folder is inside the repository at …; checking the whole repository."
- **Session start given:** base = `git rev-list -1 --before=<time> HEAD` (if none → empty tree, i.e. everything is new). Diff = `git diff <base>` (committed + uncommitted tracked changes) + content of untracked files. Commit list = `git log --oneline <base>..HEAD`.
- **No session start:** if `git status --porcelain` is non-empty → `git diff HEAD` + untracked files. Otherwise → `git diff HEAD~1 HEAD` (single-commit repo → `git show HEAD`).
- Untracked files: `git ls-files --others --exclude-standard`, shown as `+++ new file: path` with content (skip binaries / files > 100 KB).
- Diff capped at ~300,000 characters; if truncated → warning "Diff too large, some claims may be unverifiable".
- Empty diff → warning "No changes found for this period" (PRD state).
- Changed file list: `git diff --name-only <same range>` + untracked files.
Returns `ChangeSet {diff: str, files: list[str], commits: list[str], mode: str, warnings: list[str]}`.

### Claim Verifier (`verifier.py`)
Implements `prd.md > Splitting the Report Into Claims` and `prd.md > Verdicts`.
- One `generate_content` call with system instructions: split the report (any language) into atomic, checkable claims; for each give `verdict` (`done` / `not_done` / `unverifiable`), a 1–2 sentence `explanation` in the report's language, `evidence`: exact lines copied from the diff (empty if none), and `files`: repo paths the claim refers to. Claims about tests passing, running things, or behavior not visible in code → `unverifiable`.
- **Evidence check** (pure Python, testable): normalize whitespace, strip leading `+`/`-`; match evidence lines against diff lines. **Trivial lines are ignored**: fewer than ~8 non-whitespace characters, or only brackets/punctuation, `return`, `pass`, `else:`, `}` and similar. A `done` claim needs **at least one non-trivial evidence line found in the diff**; otherwise → `unverifiable`, explanation prefixed "Evidence could not be found in the diff." (Stops a ✅ passing by quoting `}`.)

### "Nothing Else Changed" Claims (`verifier.py`)
Implements `prd.md > Changes the Agent Didn't Mention`. Added at final review so the demo's key moment is deterministic.
- Gemini marks claims like "I didn't touch anything else" with `scope_claim: true` and must split compound sentences.
- `split_special_claims` (Python) also searches the report and each claim with the `NOTHING_ELSE` regex (English phrasings); a merged claim is split, a missing one is added.
- `judge_scope_claims` (Python) sets the verdict after the unmentioned-changes step: any unmentioned change → ❌ with those files' changed lines as evidence; none → ✅ "Every changed file is mentioned in the report."
- Explanations are always written in English (prompt rule).

### "Left X Untouched" Claims (`verifier.py`)
Added at final review after a real bug: "I left config.py untouched" was judged by the general rule and explained with a different file.
- `FILE_UNTOUCHED` regex finds denials that name a file ("left X untouched", "didn't touch X", "X is unchanged"); `split_special_claims` turns each into its own claim with `untouched=[X]` (also when Gemini merged it or dropped it).
- `judge_untouched_claims`: X changed → ❌ "X was changed: +a -r lines." with X's own changed lines as evidence; otherwise ✅ "X has no changes in this period."
- `_mentioned` ignores file names that appear only inside such denials, so a quietly changed X shows up in "Changes the agent didn't mention".
- The general "nothing else changed" rule applies only to phrases without a file name.

### Unmentioned Changes (`verifier.py`)
Implements `prd.md > Changes the Agent Didn't Mention`.
- Pure Python after the Gemini call: a changed file (`ChangeSet.files`) counts as *mentioned* if its path/basename appears in the **report text**, or it is in the `files` of a claim that stayed ✅ after the evidence check. Files the AI attached to ❌/⚠️ claims don't count. Everything else → `unmentioned: [{file, added, removed}]` (line counts from the diff).
- Rendered under the claims as "Changes the agent didn't mention"; hidden when empty.
- Summary counts computed in Python, not by the model (`prd.md` criterion: summary matches the list).

## Data Model
Nothing persists. Per request only:
```python
class Claim(BaseModel):
    claim: str                 # the statement from the report
    verdict: Literal["done", "not_done", "unverifiable"]
    explanation: str
    evidence: str              # exact diff lines, may be empty
    files: list[str]           # repo paths the claim refers to

# API response
{ "summary": {"total": 5, "done": 3, "not_done": 1, "unverifiable": 1},
  "claims": [Claim...],
  "unmentioned": [{"file": "src/db.py", "added": 12, "removed": 3}],
  "warnings": ["..."],
  "mode": "uncommitted vs HEAD" }
```
Form values live only in the page; lost on reload (PRD: nothing saved).

## File Structure
```
buildwithai-basics/
├── app.py                 # Flask server: routes, input validation
├── changes.py             # git commands → ChangeSet (what actually changed)
├── verifier.py            # Gemini call, evidence check, unmentioned changes, summary
├── templates/
│   └── index.html         # the one page: form + receipt container
├── static/
│   ├── style.css          # chosen theme (receipt or terminal)
│   └── app.js             # submit, loading state, render receipt
├── demo/
│   └── make_demo_repo.py  # builds a sample repo + fake lying agent report (SAMPLE DATA)
├── tests/
│   ├── test_changes.py    # temp git repos: uncommitted, multi-commit + session start, empty, Cyrillic/emoji content
│   └── test_evidence.py   # evidence check, trivial-line rule, downgrade, unmentioned files
├── requirements.txt
├── .env.example           # GEMINI_API_KEY=, GEMINI_MODEL=gemini-2.5-flash
├── README.md              # English: what, setup, run, demo
└── devpost/               # Devpost learning workspace
```

## External Services and Dependencies
**Gemini API (Google AI Studio, free tier)**
- Auth: API key in `.env` → `GEMINI_API_KEY`; `genai.Client()` reads it.
- Call: `client.models.generate_content(model=GEMINI_MODEL, contents=[prompt], config=GenerateContentConfig(system_instruction=..., response_mime_type="application/json", response_schema=Verdicts))` where `Verdicts = {report_language, claims: list[Claim]}`.
- Limits (2026 free tier, may change): Flash ~10 RPM / ~250 requests/day, 1M-token context. One check = one request.
- Cost: free. **Free-tier inputs may be used by Google to improve models** — use demo/non-sensitive repos.
- Docs: https://ai.google.dev/gemini-api/docs · rate limits: https://ai.google.dev/gemini-api/docs/rate-limits

## Important Failure Modes
- **Bad input** (empty report/path, folder missing, not a git repo) → request never reaches Gemini; message next to the field (`prd.md > States and Boundaries`).
- **Gemini fails** (no/invalid key, rate limit 429, timeout, malformed JSON) → one plain message at the top: "AI check failed: <reason>. Try again in a minute." Form keeps its values.
- **Unknown session preset / bad `session_start` (API only)** → message under the session buttons.
- **Gemini 503 (overloaded)** → one automatic retry after 2 s (`verifier.with_retry`); a second 503 shows "Gemini is overloaded right now (503). Try again in a minute."
- **Gemini invents evidence** (or quotes trivial lines like `}`) → evidence check downgrades ✅ to ⚠️.
- **Non-UTF-8 / Cyrillic / emoji in the repo** → git output decoded as UTF-8 with `errors="replace"`; never crashes.
- **No claims found** → "No checkable claims found in the report."

## What Was Simplified and Why
- **One Gemini call** instead of one sub-agent per claim — stays in free-tier limits; parallel agents are in `prd.md > Deferred From the POC`.
- **Diff-only verification** instead of reading the whole repo or running tests — the kernel is "claims vs. what changed"; tests → ⚠️.
- **Text-substring evidence check** instead of semantic diff analysis — simple, deterministic, testable.
- **One theme** kept after the preview instead of a theme switcher (`prd.md > Deferred From the POC`).

## Decisions and Open Issues
**Learner decisions:** Python; Flask + plain page (accepted recommendation); Gemini free tier; run locally, no deploy; project documents and code in English; UTF-8 git decoding; trivial-evidence rule; "Changes the agent didn't mention" section (added at spec review).
**Derived by agent (review):** single-call design; evidence check with ✅→⚠️ downgrade; git mode rules above; session start chosen with preset buttons (resolves `prd.md > Open Questions`; a date picker and then a typed date were replaced at final review — browser locale, and nobody remembers the exact time); 300K-char diff cap.
**Useful unknown:** "Can the checker itself lie?" — yes, Gemini can hallucinate just like the agent being checked. Clarified by the evidence check: the AI must quote the diff, Python confirms the quote is real. Verified in build by `tests/test_evidence.py` and by a demo claim whose fake evidence gets downgraded.
**Open:** exact free-tier Gemini model ID — verify in build step 1 (`GEMINI_MODEL`).
**Carry-over:** translate `scope.md` and `prd.md` to English before publishing (`6-ship`).
