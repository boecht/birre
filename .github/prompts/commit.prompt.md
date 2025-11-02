---
description: Commit staged changes, grouped logically
mode: git
model: GPT-5 mini (copilot)
tools: ['github/github-mcp-server/get_commit', 'github/github-mcp-server/list_commits', 'github/github-mcp-server/push_files', 'runCommands']
---
You finalize staged work with minimal back‑and‑forth. Follow this checklist each time:


1. **Check for staged changes**
   - Run `git diff --cached --numstat --shortstat && git diff --cached --name-status`.
   - If nothing is staged, report that no commit is needed and stop.
   - Read the full staged diff to understand changes.
2. **Identify logical groupings**
   - Note test/code/doc pairings and any unrelated edits.
   - Auto-split when boundaries are obvious (e.g., feature + tests vs. README tweak; separate packages/dirs; unrelated modules).
   - Keep “one topic per commit”; avoid over-atomization and kitchen-sink commits.
   - Treat unstaged files as out of scope.
3. **Write commit messages**
   - Format: `<scope>: <imperative summary>`.
   - Possible scopes: module, package, feature, or `docs(<area>)` for documentation.
   - Subject line aim ≤ 50 chars; no trailing period; blank line between subject and body.
   - Don’t include IDs in subject; reference issues/tickets in body if needed.
   - Body (when needed) explains what changed, why it matters to users or maintainers.
   - Use imperative mood, present tense; wrap body at ~72 chars.
   - Focus on user value or system impact rather than low‑level diffs.
4. **Create and verify commits**
   - Record commits for each planned group. Do not push.
5. **Report results (readable output)**
   - For each commit, print: commit id + scope, summary, body (if any), and a short file list with stats.
   - Use the example format below; keep it terse and scannable.

### Output format

Use this structure in your final message so humans can skim quickly:

```
Commit <N> [<scope>]

<subject line>

<body (if any)>

<file list with stats>
```

Example:

```
Commit bebfde6 [docs(commit-prompt)]

update instructions and checklist

Revise description to emphasize logical grouping and output clarity,
remove 'changes' tool reference, restructure checklist into 5 steps,
and add preference for GitHub MCP tools over shell commands. This
clarifies the commit workflow and aligns with current tooling
availability.

- (M)  .github/prompts/commit.prompt.md  +35 -9
```

**Tips**:
- Omit the Body section if the subject alone is sufficient.
- If multiple commits are created, number them in order (Commit 1, Commit 2, …).
- For Files, show a single‑letter status (A/M/D/R), path, and line changes (+N -M); source is `git diff…` in step 1.

**Notes**:
- Prefer GitHub MCP tools for Git operations; fall back to shell only if a capability is missing.
- Never modify files to satisfy hooks; never use `--no-verify`
- Rely on the live staged state; ignore any previously saved snapshots.
- When splitting commits, err on the side of clarity: docs tweaks separate from code changes; unrelated modules in separate commits.
