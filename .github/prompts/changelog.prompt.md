---
description: Draft and insert a CHANGELOG entry from recent changes
mode: git
tools: [
  'edit/editFiles',
  'runCommands',
  'search',
  'crash/*',
  'github/github-mcp-server/get_commit',
  'github/github-mcp-server/get_file_contents',
  'github/github-mcp-server/get_label',
  'github/github-mcp-server/get_latest_release',
  'github/github-mcp-server/get_release_by_tag',
  'github/github-mcp-server/get_tag',
  'github/github-mcp-server/list_branches',
  'github/github-mcp-server/list_commits',
  'github/github-mcp-server/list_pull_requests',
  'github/github-mcp-server/list_releases',
  'github/github-mcp-server/list_tags',
  'github/github-mcp-server/pull_request_read',
  'github/github-mcp-server/search_pull_requests',
  'think',
  'changes',
  'todos'
]
---

## Goal

You will update or create a [`CHANGELOG.md`](../../CHANGELOG.md) entry that follows BiRRe standards

## Rules

You MUST strictly follow the rules in [edit-changelog.instructions.md](../instructions/edit-changelog.instructions.md)
Non-compliance will result in rejected entries. Pay special attention to:

1. **Comprehensive coverage**: Analyze ALL commits on the branch (not just the latest one!)
2. **Category order**: Changed, Added, Deprecated, Removed, Fixed, Security (EXACT order, no exceptions)
3. **Imperative mood**: "Add feature" NOT "Added feature" or "New feature added"
4. **User benefits**: Describe impact, not implementation details

## Inputs (from user)

- version (e.g., 4.0.0-alpha.3) — if omitted: try to extract from branch name, otherwise bump released patch version
- date (YYYY-MM-DD) — if omitted: use today

## Playbook

### Gather context

- Enumerate ALL commits on the current branch (= all commits since the last merge into main)
- Review EACH commit to identify user-facing changes (don't stop at the most recent commit!)
- Skim the commit messages and, if required, diffs to understand user-facing effects

### Categorize

- Use the six categories in this EXACT order: Changed, Added, Deprecated, Removed, Fixed, Security
- Use imperative mood for ALL bullets (e.g., "Add X", "Fix Y", "Remove Z" — NOT "Added", "Fixed", "Removed")
- Describe user impact (not implementation): "Improve startup time" not "Refactor config loader"
- Mark breaking changes with `**Breaking:**` under Changed/Removed

### Write the entry

- Insert (or update) a section:
  - `## [<version>] - <date>`
  - Categories only if they have items; omit empty categories
- Keep it self-contained; avoid internal codes and commit dumps

### Save

- Update [`CHANGELOG.md`](../../CHANGELOG.md) in place
- Provide the diff of the inserted section

## Reference

- See full rules at [edit-changelog.instructions.md](../instructions/edit-changelog.instructions.md)
