---
doc: checklist
status: approved
---

# Build Checklist

Build mode: fast

## Slices

- [x] **1. Paste a report and a repo path, get claims with verdicts**
  Becomes usable: A running local page where a pasted agent report + repo path returns a plain list of claims with ✅ / ❌ / ⚠️ and explanations, using uncommitted-vs-HEAD or last-commit diff.
  Why now: This is the kernel and the biggest risk (Gemini free-tier model ID, structured JSON, git on Windows). If it works, everything else is polish around it; if it doesn't, we learn now.
  PRD ref: `prd.md > The Core Journey`, `prd.md > Splitting the Report Into Claims`, `prd.md > Verdicts`
  Spec ref: `spec.md > Flask Server (app.py)`, `spec.md > Choosing What Counts as "Changed" (changes.py)`, `spec.md > Claim Verifier (verifier.py)`, `spec.md > External Services and Dependencies`, `spec.md > File Structure`
  Build: Scaffold `requirements.txt`, `.env.example`, `app.py`, `changes.py` (UTF-8 git helper; no-session-start modes + untracked files), `verifier.py` (one Gemini call with `response_schema`, Python-computed summary), `templates/index.html` + minimal `static/app.js` rendering. Confirm a working free-tier model ID and set it as the `GEMINI_MODEL` default.
  Verify (mechanical): `python -c` lists/pings the chosen model; start `python app.py`; POST a sample report against a temp git repo with a known change and a known lie → response JSON contains ≥1 `done` and ≥1 `not_done`, summary counts match claims.
  Learner check: Open http://localhost:5000, paste a short report about changes you made in any git folder, press Check, and see whether the verdicts match reality.
  Commit: `Check agent report claims against git diff with Gemini`

- [x] **2. The receipt looks like yours — pick the theme**
  Becomes usable: Summary line, claim rows with verdict icon, explanation and colored diff snippet; both themes (receipt / terminal) previewable, then one kept.
  Why now: The PRD defers the design choice until Dmytro sees both; deciding early shapes every later visible element.
  PRD ref: `prd.md > Screens and Layout`, `prd.md > Look and Feel`
  Spec ref: `spec.md > Look and Feel`, `spec.md > Web Page (templates/index.html, static/app.js, static/style.css)`
  Build: Style form + receipt with CSS custom properties for both themes, a temporary `?theme=` switch for preview; render summary, stamps/icons, `+`/`-` colored diff snippets. After Dmytro picks, remove the other theme and the switch.
  Verify (mechanical): Page loads with no console errors in both themes (Playwright snapshot); rendered summary counts equal the number of rows of each verdict.
  Learner check: Open both `?theme=receipt` and `?theme=terminal` with the same result, pick one, say what you'd change.
  Commit: `Style the receipt with the chosen theme`

- [x] **3. The checker can't be fooled, and silent changes show up**
  Becomes usable: A ✅ without real, non-trivial evidence becomes ⚠️; files changed but never mentioned appear under "Changes the agent didn't mention".
  Why now: This is what makes the verdicts trustworthy — the "who checks the checker" answer from the spec — and it closes the "changed it quietly" pain.
  PRD ref: `prd.md > Verdicts`, `prd.md > Changes the Agent Didn't Mention`
  Spec ref: `spec.md > Claim Verifier (verifier.py)`, `spec.md > Unmentioned Changes (verifier.py)`, `spec.md > Data Model`
  Build: Evidence check with whitespace normalization and trivial-line rule; `files` in the Claim schema; unmentioned-files computation with added/removed counts; render the block (hidden when empty); `tests/test_evidence.py`.
  Verify (mechanical): `pytest tests/test_evidence.py` passes (fake evidence → downgraded, `}`-only evidence → downgraded, real line → stays done, unmentioned file detected, all-mentioned → empty).
  Learner check: Change a file you don't mention in the report, run a check, and see it listed as an unmentioned change.
  Commit: `Verify evidence against diff and list unmentioned changes`

- [x] **4. Session start time catches every commit of the agent's session**
  Becomes usable: Optional "Session start" field; with it, all commits after that time plus uncommitted changes are checked.
  Why now: Agents often auto-commit several times; without this, honest work looks like ❌.
  PRD ref: `prd.md > What Counts as a Change (Comparing With Git)`
  Spec ref: `spec.md > Choosing What Counts as "Changed" (changes.py)`
  Build: `datetime-local` input; `git rev-list -1 --before=` base (empty tree fallback); commit list; 300K cap with warning; `tests/test_changes.py` with temp repos (uncommitted, multi-commit + start time, empty, Cyrillic/emoji content).
  Verify (mechanical): `pytest tests/test_changes.py` passes.
  Learner check: Make two commits in a test folder, set the start time before them, and see claims from both commits confirmed.
  Commit: `Support session start time and multi-commit sessions`

- [x] **5. Bad input and failures explain themselves**
  Becomes usable: Empty fields, missing folder, non-git folder, no changes, no claims, Gemini errors — each shows a clear message; loading state disables the button.
  Why now: After the happy path is solid; these are the states from the PRD that a demo viewer or first user will hit.
  PRD ref: `prd.md > States and Boundaries`
  Spec ref: `spec.md > Important Failure Modes`
  Build: Validation in `app.py` returning `{error, field}`; per-field messages and top-level AI error in `app.js`; warnings banner; first-use hint.
  Verify (mechanical): POST each bad input with Flask test client → correct error/field; missing API key → clear AI error, no crash.
  Learner check: Try an empty report, a random non-git folder, and a folder with no changes; each message should tell you what to do.
  Commit: `Handle bad input and AI failures with clear messages`

- [x] **6. One command sets up the demo**
  Becomes usable: `python demo/make_demo_repo.py` creates a sample repo with a lying agent report (labeled SAMPLE DATA); README explains setup, run and demo.
  Why now: Last — it packages the finished behavior for the video and the public repo.
  PRD ref: `prd.md > Demo Scenario`
  Spec ref: `spec.md > Where It Runs and How Someone Tries It`, `spec.md > File Structure`
  Build: Demo script (repo with real change, an unmentioned change, a fake claim, a "tests passed" claim); English `README.md`.
  Verify (mechanical): Run the script, POST its report → at least one ✅, one ❌, one ⚠️ and one unmentioned file.
  Learner check: Follow the README from scratch and record a dry run of the demo.
  Commit: `Add demo repo script and README`

## Hands-on Checkpoints

- [x] Early usable behavior explored — after slice 2 (real verdicts + chosen theme). Feedback: Terminal theme; ignore `.playwright-mcp/`; explanations must match report language (fixed); unmentioned block expected (arrives in slice 3); dark theme on screen recording — record at higher zoom (for `6-ship`).
- [x] Final kick-the-tires exploration and feedback completed — three feedback rounds, see Final Review

## Final Review

Round 1 (Dmytro): new files always ⚠️ → fixed (real content of new files as evidence; model sees diff without git headers). Everything in English → done, checked 3 times.
Round 2 (Dmytro):
- [x] Explanations always in English
- [x] "Nothing else changed" judged deterministically by Python; compound claims split (tests/test_scope_claims.py)
- [x] Session start as `YYYY-MM-DD HH:MM` text field with validation; "Compared:" without T
- [x] Terminal window frame, green ▶ RUN CHECK, ✓ ✗ ! badges before the claim, pytest-style summary, amber unmentioned block, no "No such change found.", lower report field
Round 3 (Dmytro):
- [x] Session presets (Auto · Last hour · Last 3 hours · Today · Yesterday) instead of typing a date; demo commits are now relative to the current time ("Last hour")
- [x] "I left config.py untouched" checked against config.py itself; file named only in a denial counts as unmentioned (tests/test_untouched_claims.py; reproduced and fixed on Dmytro's my-check-repo)
- [x] One automatic retry on Gemini 503
- [x] Palette chosen: Dracula (switcher and other palettes removed)
Retried by Dmytro: config.py bug fixed on my-check-repo (2 runs), demo via Last hour 1 ✓ / 3 ✗ / 1 !, honest Ukrainian report all ✓ with English explanations, presets convenient.

- [x] Final review complete — feedback resolved and learner confirms ready to ship (said "ready" after round 3)

## Code Tour and App Map

- [x] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [x] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [x] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: Focused alternative — traced the config.py bug from PRD criterion (`prd.md > Changes the Agent Didn't Mention`) to `tests/test_untouched_claims.py > test_bug_report_scenario` to the re-run on a real repo. Learner ran/read the test and identified what it proves (Python corrects the verdict regardless of the model) and what it doesn't (English-only phrasing, no real Gemini call; also phrasings without a file extension).
Route and stops: Reference route in the app map: `changes.py > collect_changes` → `verifier.py > FILE_UNTOUCHED / split_special_claims` → `verifier.py > judge_untouched_claims / _mentioned`.
Edit outcome: Not applicable (focused alternative, no edit).
Reflection: Already covered by the learner's own observation; extra question skipped.
Activity mode: Focused alternative using a real test and real-repo results.

## Revisions
- Default model `gemini-3.5-flash-lite` instead of `gemini-2.5-flash` — free-tier limits in Dmytro's AI Studio: 2.5 Flash not available for free; 3.5 Flash Lite gives 15 RPM / 500 per day; Gemma 4 rejected (16K TPM too small for diffs).
- Gemini response wrapped in `Verdicts {report_language, claims}` — with a plain list, explanations sometimes came back in the language of Cyrillic comments in the diff instead of the report's language.
- Folder inside a larger repo → check the whole repo from its root and show a warning — tests found that the developer's home folder is itself a git repo, so any folder under it counted as "a repository", and git mixed path bases in subfolders.
- "Mentioned" now means named in the report text or covered by a verified ✅ claim — in the demo, Gemini attached the quietly changed `settings.py` to the ❌ claim "I didn't change anything else", which hid it from the unmentioned block.
- Session start is a text field instead of `datetime-local` — the browser date picker shows the browser's locale ("dd.mm.yyyy" in Ukrainian), not the English UI.
- "Nothing else changed" claims are judged by Python, not Gemini — in the demo the model sometimes merged "All tests pass and I didn't change anything else" into one ⚠️ and the lie about settings.py went uncaught.
- Session presets instead of a typed start time — nobody remembers when the agent session started; Auto stays the default.
- File-specific denials ("left config.py untouched") get their own rule — the general "nothing else changed" rule explained such a claim with a different file (notes_todo.txt) and never showed the config.py change.
