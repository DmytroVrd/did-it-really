---
doc: scope
status: approved
---

# Did it really?

A local web app: paste a coding agent's final report, point it at a local folder with a git repository, and see which of its claims are true and which are not.

## The Unique Kernel
The agent's report is split into **individual claims**, and each one is checked against **what actually happened in git** (committed and uncommitted changes compared with the previous state, and whether the code exists). Each claim gets a verdict — ✅ done / ❌ not done / ⚠️ can't be verified — with a short explanation of *why*.
The difference from "ask another agent to check": no need to write a long prompt or explain the history — just drop in the report and the folder.

## Who It's For
First, Dmytro himself: he writes code with several agents, and they often say "all done, nothing broken" when in fact they quietly changed something, made something up, or didn't do it. Today he writes a separate agent a long "review every file" prompt, and that agent doesn't know the history.
Later: publish it as an open repository (app / skills) so beginners, professionals, and people who don't write code themselves but want to check an agent's work can pick it up.

## The Core Loop
The agent finishes → you copy its final message → paste it into the app and point it at the local project folder (with `.git`) → within a couple of minutes you see a list of claims with verdicts and explanations → you know what to trust and what to check or redo.
You come back after every session with an agent.

## Inspiration & Identity
Like a receipt: a clear list, each line a green check, a red cross or a yellow ⚠️, plus one or two sentences of explanation. Short, honest, no filler.

## Why This Matters to the Learner
His own pain: "what the agent says isn't necessarily what's there." He read an article about this problem and wanted to close the gaps in existing solutions with a tool of his own.

## What "Working" Looks Like
Dmytro opens the app locally, pastes a report where the agent says "all done", points it at the repository — and within a few minutes a list appears: some ✅, but also ❌ and ⚠️, each with an explanation.
**The "wow" moment for the video:** the agent confidently says "everything is done", and the receipt lights up red exactly where it lied.

## The POC Boundary
- One page: a field for the report + the path to a local folder with a git repository (changes come from the local `.git`, no GitHub).
- Splitting the report into individual claims.
- Checking each one through git (diff of committed/uncommitted changes against the previous state) and file contents.
- Result: a list of claims with ✅ / ❌ / ⚠️ and a short explanation.
- Claims that can't be checked from code (e.g. "all tests pass") → ⚠️ with an explanation.

## Later
- The app runs the tests itself to check "tests pass".
- Parallel sub-agents, each checking its own claim.
- GitHub integration (checking PRs, commenting on PRs).
- Publishing openly (repository / skills) for other people.

## Explicitly Cut
- **Deployment / hosting** — the tool is local and works with your folder; not needed for the demo.
- **Accounts, check history** — not needed to prove the idea.
- **MCP server / editor integration** — those already exist; Dmytro wants his own standalone app.
