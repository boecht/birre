---
description: Prep a release from a dev branch with an active PR
mode: git
tools: ['changes', 'github/github-mcp-server/push_files', 'github/github-mcp-server/list_commits', 'github/github-mcp-server/get_commit', 'runCommands']
---
Given context: you’re on a dev branch with multiple existing changes and an active PR.
Prepare the branch for release with minimal interaction.

Inputs (from user):
- next_version (e.g., 4.0.0-alpha.3)

Checklist

1. Changelog up to date

- Check `CHANGELOG.md` contains a section for `<next_version>` in the six-category format.
- If missing or style violations are obvious, state what’s needed and stop.

2. Versions bumped

- Confirm `pyproject.toml [project].version` equals `<next_version>`.
- Confirm runtime `__version__` exists in `src/birre/__init__.py` and equals `<next_version>`.
- If any of the versions are missing or incorrect, mention which files need updating and stop.

3. Run tests

- Offline: `uv run pytest --offline`.
- Online: `uv run pytest --online-only` (assume `BITSIGHT_API_KEY` exported).
- Online selftest: `uv run birre selftest --production`.
- If failures occur, report and stop.

4. Stage any updated artifacts

- If tests or tooling updated tracked files (e.g., snapshots), include them.

5. Commit and push

- Create commit: `Bump version to v<next_version>` including all staged files.
- Push the dev branch.

6. Next step for user

- Instruct: Approve/merge the open PR into `main`.
- Provide tag command to run after the merge on the main branch:
  - Bash: `git tag v<next_version> && git push origin v<next_version>`

Notes
- Use `changes` to verify staged content; use `push_files` to create the commit; use `list_commits`/`get_commit` to report hashes.
- Keep responses concise: checks → actions → results.
