---
description: Run BiRRe selftest and summarize diagnostics
mode: agent
tools: ['runCommands']
---
You will run the BiRRe self test and provide a concise diagnostic summary.

Checklist

1. Run selftest
   - Execute: `uv run birre selftest`
   - If the user requests production: `uv run birre selftest --production`

2. Summarize results
   - Report configuration summary, connectivity checks, subscription tests, and any warnings/errors
   - Provide actionable next steps for each failure.

3. Optional: targeted runs
   - If asked, re-run with flags (`--offline`, `--debug`) and summarize differences

Output format
- One-paragraph status + short bullet list of issues (if any) with fixes.
