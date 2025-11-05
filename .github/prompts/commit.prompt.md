---
description: Commit staged changes, grouped logically
mode: git
model: GPT-5 mini (copilot)
tools: [
  'github/github-mcp-server/get_commit',
  'github/github-mcp-server/list_commits',
  'github/github-mcp-server/push_files',
  'runCommands'
]
---

## Goal

You finalize staged work with minimal back‑and‑forth.

## Rules

Treat every invocation as brand new: never reuse prior answers, cached data, or previous command output.

## Playbook

Follow this playbook exactly and in order; do every step during this run, even if it feels redundant.

### Inspect the staged index

- Use `runCommands` to execute the following commands in order during this invocation:
  - `git diff --cached --numstat --shortstat && git diff --cached --name-status`
  - `git diff --cached -U2 --minimal --no-color | head -n 1000`
- Do not alter the commands or add any others, use them exactly as given
- If the commands show nothing staged, report that no commit is needed and stop
- Read the diff output so you understand what will be committed

### Plan logical commit groupings

- Pair code with its matching tests and docs; split when changes target different features, packages, or directories
- Auto-split obvious mixes (e.g., feature + tests vs. README tweak, refactor vs. version bump)
- Keep “one topic per commit”; err on clarity over granularity
- Treat unstaged files as out of scope

### Draft commit messages

- Subject format: `<scope>: <imperative summary>` (≤ 50 chars, no trailing period)
- Scope can be a module/package name or `docs(<area>)` for documentation-only commits
- Leave one blank line between subject and body; wrap body text at ~72 chars
- Skip ticket/issue IDs in the subject; reference them in the body if needed
- Write in imperative, present tense, focusing on user or maintainer impact

### Record and validate commits

- Create the planned commits; never push
- Afterwards run `git status --short` via `runCommands`. If anything remains staged, loop back to Step 2 to regroup

### Report results

- Output one block per commit using the template below.
- Do not add introductions, validation summaries, next-step offers, or any other commentary unless
  a previous step failed. When a failure occurs, report the failure instead of commit details

## Output format

Use this structure in your final message so humans can skim quickly:

```text
### Commit <short commit SHA> [<scope>]

<subject line>

<body (if any)>

<file list with stats>
```

### Example

```text
### Commit bebfde6 [docs(commit-prompt)]

update instructions and checklist

Revise description to emphasize logical grouping and output clarity,
remove 'changes' tool reference, restructure checklist into 5 steps,
and add preference for GitHub MCP tools over shell commands. This
clarifies the commit workflow and aligns with current tooling
availability.

- (M)  .github/prompts/commit.prompt.md  +35 -9
```

### Tipps for filling the template

- Use the first seven characters of each commit SHA reported by `git commit`.
- Show files as `<status>  <path>  +N -M`, pulling stats from the staged diff.

## Notes to remember throughout

- Prefer GitHub MCP tools; fall back to shell only if a capability is missing
- Never modify files to satisfy hooks and never use `--no-verify`
- Work strictly from the current staged state; ignore unstaged or cached snapshots
- When splitting commits, err on the side of clarity: unrelated modules in separate commits
