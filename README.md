# Did it really?

**Your coding agent says "Done! All tests pass, nothing else changed." Did it really?**

A small local web app that takes an AI coding agent's final report, splits it into individual claims and checks each one against what actually changed in your git repository.

```
==== 1 verified · 3 not found · 1 unverifiable ====

✓ VERIFIED      Added complete_task(index) to tasks.py
✗ NOT FOUND     Added validation to add_task so empty titles raise ValueError
✗ NOT FOUND     Updated the README with usage examples
! UNVERIFIABLE  All tests pass
✗ NOT FOUND     I didn't change anything else
                1 changed file is not mentioned in the report: settings.py.

┌ Changes the agent didn't mention ┐
│ settings.py +2 -2                │
└──────────────────────────────────┘
```

## How it works

1. You paste the agent's final message, the path to your project folder, and pick the agent session.
2. The app runs plain `git` commands in that folder to collect what really changed:
   - **Auto** (default) → uncommitted changes vs the last commit (or, if everything is committed, the last commit vs the previous one);
   - **Last hour / Last 3 hours / Today / Yesterday** → every commit made since then, plus uncommitted changes.
   New untracked files are included.
3. One request to **Gemini** splits the report into claims and gives each a verdict — ✓ verified, ✗ not found, ! unverifiable from code (e.g. "tests pass") — with a short English explanation and the diff lines that prove it. The report itself can be in any language.
4. **The checker is checked too.** Python confirms that every quoted evidence line really exists among the changed lines of the diff. Trivial quotes like `}` or `return` don't count. A ✓ without real evidence becomes !.
5. Files changed in the diff that the agent never named are listed under **"Changes the agent didn't mention"**.
6. **Denials are judged by Python, not the AI.** "I left config.py untouched" is ✗ if config.py changed (with its own diff as proof); "I didn't change anything else" is ✗ if there are unmentioned changes.

Nothing is stored. Reload the page and the result is gone.

## Setup

Requires Python 3.11+, git, and a free Gemini API key from <https://aistudio.google.com/apikey>.

```
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Put your key in `.env`:

```
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash-lite
```

## Run

```
python app.py
```

Open <http://localhost:5000>.

## Try the demo

```
python demo/make_demo_repo.py
```

This creates a **sample** repository (in your temp folder) where an "agent" made two commits in the last hour: it added one function, quietly changed `settings.py`, and then reported more than it did. The script prints the repository path and the agent report — paste them into the app, pick **Last hour** and press **▶ RUN CHECK**.

## Tests

```
python -m pytest
```

Tests cover the git logic (uncommitted changes, multi-commit sessions, Cyrillic/emoji, huge diffs, subfolders), the evidence check, the "untouched" / "nothing else" rules, session presets and the input/error handling. They don't call Gemini.

## Limits

- Verification is based on the diff only. The app doesn't run your tests, so claims like "all tests pass" are marked unverifiable.
- "Untouched" / "nothing else" phrases are recognized in English; in other languages it depends on Gemini flagging them.
- One Gemini request per check (one automatic retry if Gemini answers 503). Free-tier limits apply (for `gemini-3.5-flash-lite`: about 15 requests/minute, 500/day).
- On the Gemini free tier Google may use your prompts to improve its models. Your diff is sent to Gemini, so use it on code you're allowed to share.
- Very large diffs are cut at 300,000 characters, with a warning.

## Project structure

```
app.py              Flask server: page, /api/check, input validation
changes.py          git commands → what actually changed
verifier.py         Gemini call, evidence check, unmentioned changes, summary
templates/index.html
static/app.js       form, loading state, rendering the result
static/style.css    terminal-window theme
demo/               sample repository generator
tests/              pytest tests
devpost/            planning documents (scope, PRD, spec, build checklist)
```
