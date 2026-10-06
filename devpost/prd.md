---
doc: prd
status: approved
---

# Did it really? — Product Requirements

A local web app for developers who work with coding agents: paste the agent's final report, point it at a local git folder, and see a "receipt" where every claim the agent made is marked ✅ / ❌ / ⚠️ with an explanation and evidence from the diff.
Source: `scope.md > The Unique Kernel`, `scope.md > The Core Loop`.

## The Core Journey
1. The user starts the app locally and opens it in the browser.
2. They see one page in a terminal-window frame: a field for the agent's report, a field for the repository folder path, agent-session buttons (**Auto** · Last hour · Last 3 hours · Today · Yesterday), and a **▶ RUN CHECK** button.
3. They paste the agent's final message (in any language), enter the path, and press Check.
4. While the check runs, they see that the app is working (a check can take up to a few minutes).
5. The **receipt** appears: a summary at the top, then the list of claims with verdict, explanation and evidence.
6. The user sees what can be trusted, what the agent didn't do, and what they need to check themselves.

## Screens and Layout
One page, top to bottom:
- **Form:** large "Agent report" text field; "Repository path" field; "Session start (optional)" field; "Check" button.
- **Receipt (appears after a check):**
  - Summary, e.g. "5 claims: 3 ✅ · 1 ❌ · 1 ⚠️".
  - List of claims. Each row: verdict icon, the claim itself, a short explanation of *why*, and below it the diff snippet that proves it, or "No such change found."

## Look and Feel
Two directions — Dmytro would choose after **seeing both on screen** at the start of the build ("hard to picture in my head, I need to see it"). **Chosen in build: Terminal** — at final review refined into a terminal window (● ● ● title bar), ✓ ✗ ! badges, pytest-style summary, Dracula palette.
- **Receipt:** monospace font, white or calm light background that's easy on the eyes, dashed separators, VERIFIED / NOT FOUND "stamps".
- **Test report / terminal (chosen):** dark theme, green / red / yellow, like test results in a terminal.
Verdict icons in either variant: ✅ / ❌ / ⚠️.

## Features and Behavior

### Splitting the Report Into Claims
The app finds the individual checkable claims in the report ("added function X", "changed file Y", "all tests pass", "didn't touch anything else"). The report can be in any language; **explanations are always in English** (decided at final review). Compound sentences are always split: "All tests pass and I didn't change anything else" is two claims.
- [ ] A report with several actions produces a separate row per claim, not one combined row.
- [ ] Reports in Ukrainian and in English are both split correctly.

### What Counts as a Change (Comparing With Git)
Source: `scope.md > The POC Boundary`.
- **A session preset chosen** (Last hour, Last 3 hours, Today, Yesterday — replaced the typed date at final review: nobody remembers the exact time) → check every commit made after that point **plus** uncommitted changes.
- **Auto (default)** → if there are uncommitted changes, compare them with the last commit; if everything is committed, compare the last commit with the previous one.
- [ ] The agent made 3 commits during the session and a start time is given → changes from all three are included.
- [ ] Uncommitted changes → they show up in the check.

### Verdicts
- **✅ Done** — the changes contain evidence; the matching diff snippet is shown.
- **❌ Not done** — the changes don't contain it (or it was done differently than claimed); the explanation says what's missing.
- **⚠️ Can't be verified** — can't be established from code (e.g. "all tests pass"); the explanation says why.
- [ ] Every claim has exactly one verdict and a non-empty explanation.
- [ ] Every ✅ has a diff snippet as evidence.
- [ ] The summary at the top matches the number of verdicts in the list.

### Changes the Agent Didn't Mention
Added at the spec review. Below the list of claims, a "Changes the agent didn't mention" block: files changed in the diff that no claim refers to (with added/removed line counts). Directly addresses the "changed it quietly" pain.
- [ ] The agent changed a file without mentioning it in the report → the file appears in this block.
- [ ] The report says "I left config.py untouched" / "didn't touch config.py" while config.py changed → that claim is ❌ with config.py's own diff as evidence, and config.py is listed as unmentioned (a file named only in a denial doesn't count as mentioned).
- [ ] The report says "I didn't change anything else" while unmentioned changes exist → that claim is ❌, decided by the app itself (not the AI), with the unmentioned files' changed lines as evidence. If every changed file is mentioned → ✅.
- [ ] Every changed file is mentioned → the block is not shown.

### Demo Scenario
Source: `scope.md > What "Working" Looks Like`.
- [ ] On a prepared repository, an "all done" report produces at least one ❌ where the agent really didn't do what it claimed, and ✅ where it did.

## States and Boundaries
*(Marked as assumptions — Dmytro delegated the obvious cases; confirmed at review.)*
- **First open** — empty form with a short hint: "Paste the agent's final message and the path to your project folder."
- **Check in progress** — the button is disabled and it's visible that the app is working.
- **Empty report or empty path** — the check doesn't start; a message appears next to the field.
- **Folder doesn't exist / isn't a git repository** — a clear message: "There is no git repository in this folder."
- **No changes found** — the check still runs: claims about changes get ❌, and a visible warning at the top says "No changes found for this period."
- **No checkable claims in the report** — message: "No checkable claims found in the report."
- **Nothing is saved** — after a page reload the receipt is gone.

## Product Decisions
- One page, form + receipt — a simple "paste → check → see" loop.
- Evidence (a diff snippet) under each claim — so the verdict doesn't have to be taken on faith.
- ✅ / ❌ / ⚠️ instead of 👁️ — ⚠️ is clearer to Dmytro.
- Local git only, no GitHub.
- Multiple commits are caught by **time** (session start) — Dmytro's idea.
- Any report language; explanations always in English.
- Tests are not run — "tests pass" → ⚠️.
- The design is chosen between two variants after a visual comparison.

## What We're Building
Form (report, path, optional time) → split the report into claims → check against git changes → receipt with summary, verdicts, explanations and diff snippets → unmentioned changes block → clear messages for input errors. One visual theme.

## Deferred From the POC
- **Theme switcher (light/dark)** — two full themes instead of one; one is enough to prove the idea.
- **Running tests** — the hardest part, not needed to prove the kernel (`scope.md > Later`).
- **Parallel sub-agents per claim** — an optimization, not the idea.

## Possible Later Enhancements
- GitHub integration (checking PRs, comments).
- Publishing as an open repository / skills for others.
- Check history.

## Non-Goals
- Deployment / hosting — the tool is local.
- Accounts.
- MCP server / editor plugin — those already exist.
- Fixing code — the app only checks; it never changes anything in the repository.

## Open Questions
- ~~How exactly the user enters the session start (date+time, "last N hours"?)~~ — resolved in `4-spec`: a `datetime-local` date and time field.
