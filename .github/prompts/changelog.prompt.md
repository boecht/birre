---
description: Draft and insert a CHANGELOG entry from recent changes
mode: git
tools: ['runCommands', 'crash/*', 'github/github-mcp-server/get_commit', 'github/github-mcp-server/get_latest_release', 'github/github-mcp-server/list_branches', 'github/github-mcp-server/list_commits', 'github/github-mcp-server/list_pull_requests', 'github/github-mcp-server/list_releases', 'github/github-mcp-server/list_tags', 'github/github-mcp-server/pull_request_read', 'github/github-mcp-server/search_pull_requests', 'think', 'changes']
---
You will create a new `CHANGELOG.md` entry that follows BiRRe standards.

Inputs (from user):

- version (e.g., 4.0.0-alpha.3)
- date (YYYY-MM-DD) if different from today

Checklist

1. Gather context

- Enumerate commits on the current branch (= all commits since the last merge into main).
- Skim the commit messages and, if required, diffs to understand user-facing effects.

2. Categorize

- Place items under the six categories in order: Changed, Added, Deprecated, Removed, Fixed, Security.
- Use imperative mood and describe user impact (not implementation).
- Mark breaking changes with `**Breaking:**` under Changed/Removed.

3. Write the entry

- Insert (or update) a section:
  - `## [<version>] - <date>`
  - Categories only if they have items; omit empty categories.
- Keep it self-contained; avoid internal codes and commit dumps.

4. Save

- Update `CHANGELOG.md` in place.
- Provide the diff of the inserted section.

Reference
- See full rules at .github/instructions/edit-changelog.instructions.md
