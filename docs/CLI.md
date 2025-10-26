# Command Line Reference

BiRRe's Typer CLI is exposed through `server.py`. Use the explicit `run` subcommand to start the FastMCP server after performing startup checks:

```bash
uv run server.py run
```

Use `uv run server.py --help` to see a generated summary of the command tree at any time.

## Configuration precedence

Configuration values layer in the following order (lowest → highest):

1. `config.toml`
2. `config.local.toml`
3. Environment variables
4. CLI flags

Environment variables are mirrored by CLI options. The sections below highlight the most frequently used flags together with their corresponding environment keys.

## Shared options

Most commands accept the same core options for authentication, runtime behaviour, and logging. The table below lists the common flags and how they map to environment variables.

| Option | Environment | Description |
| --- | --- | --- |
| `--config PATH` | `BIRRE_CONFIG` | Load settings from an alternative TOML file (defaults to `config.toml`). |
| `--bitsight-api-key TEXT` | `BITSIGHT_API_KEY` | API key used to authenticate against BitSight. |
| `--subscription-folder TEXT` | `BIRRE_SUBSCRIPTION_FOLDER` | Override the folder used for ephemeral subscriptions. |
| `--subscription-type TEXT` | `BIRRE_SUBSCRIPTION_TYPE` | Override the BitSight subscription type used for temporary access. |
| `--context [standard\|risk_manager]` | `BIRRE_CONTEXT` | Select the MCP persona exposed to clients. |
| `--risk-vector-filter TEXT` | `BIRRE_RISK_VECTOR_FILTER` | Comma-separated BitSight risk vectors used when selecting findings. |
| `--max-findings INTEGER` | `BIRRE_MAX_FINDINGS` | Limit the number of findings returned with each rating payload. |
| `--skip-startup-checks / --require-startup-checks` | `BIRRE_SKIP_STARTUP_CHECKS` | Disable BitSight connectivity checks (use `--require-startup-checks` to override a configured skip). |
| `--debug / --no-debug` | `BIRRE_DEBUG` | Emit verbose diagnostic logging and payload details. |
| `--allow-insecure-tls / --enforce-tls` | `BIRRE_ALLOW_INSECURE_TLS` | Skip TLS verification when connecting to BitSight. |
| `--ca-bundle PATH` | `BIRRE_CA_BUNDLE` | Provide a custom certificate authority bundle for TLS verification. |
| `--log-level TEXT` | `BIRRE_LOG_LEVEL` | Set the logging level (e.g. `INFO`, `DEBUG`). |
| `--log-format [text\|json]` | `BIRRE_LOG_FORMAT` | Choose between human-readable and JSON log formatting. |
| `--log-file PATH` | `BIRRE_LOG_FILE` | Write logs to a file (set to `-`, `stderr`, `stdout`, or `none` to disable file logging). |
| `--log-max-bytes INTEGER` | `BIRRE_LOG_MAX_BYTES` | Maximum size for log rotation when file logging is enabled. |
| `--log-backup-count INTEGER` | `BIRRE_LOG_BACKUP_COUNT` | Number of rotated log archives to keep. |

## Commands

### `run`

Starts the MCP server with the provided configuration. The command performs offline configuration validation and optional online startup checks against BitSight. Add `--profile PATH` to capture a Python cProfile output for the run.

Example:

```bash
uv run server.py run --context risk_manager --log-format json
```

### `selftest`

Executes BiRRe's diagnostics without starting the server. It loads configuration in the same way as `run`, reports effective values, and (unless `--offline` is supplied) performs live BitSight checks against the testing API base URL by default. Use `--production` to target the production API, or `--offline` to skip network requests entirely.

Example:

```bash
uv run server.py selftest --offline
```

Exit codes:

- `0` – all checks passed
- `1` – failures detected
- `2` – completed with warnings (e.g. missing optional tools)

### `config`

Group of subcommands for inspecting and managing configuration files:

- `config show` – Displays configuration sources, environment overrides, CLI overrides, and the fully resolved configuration using Rich tables. Helpful when troubleshooting how values from different layers combine.
- `config validate` – Validates a TOML configuration file before use. With `--minimize`, BiRRe rewrites the file using its canonical layout while keeping a `.bak` backup. Passing `--debug` prints the parsed data structure.
- `config init` – Interactively generates or updates a configuration file (defaults to `config.local.toml`; override with `--config`), prompting for key values and summarizing the resulting file.

Examples:

```bash
uv run server.py config show --config myconfig.toml
uv run server.py config validate --config config.local.toml --minimize
uv run server.py config init --config custom.local.toml
```

### `logs`

Grouped log management utilities:

- `logs path` – Print the resolved active log file path after applying config/env overrides.
- `logs clear` – Truncate the active log file without touching archived rotations.
- `logs rotate` – Force a rotation using the configured (or overridden) backup count.
- `logs show` – Tail or filter the log stream. Supports:
  - `--level LEVEL` – Minimum severity (e.g. `WARNING`).
  - `--tail N` – Number of trailing entries (`0` shows the full file).
  - `--since TIMESTAMP` – ISO 8601 timestamp anchor.
  - `--last WINDOW` – Relative window such as `30m`, `2h`, `1d`.
  - `--format json|text` – Interpret entries as JSON or plain text (auto-detected by default).

Examples:

```bash
uv run server.py logs path
uv run server.py logs rotate
uv run server.py logs show --level WARNING --last 1h --format json
uv run server.py logs clear
```

### `version`

Prints the installed BiRRe package version. Falls back to reading `pyproject.toml` when BiRRe is executed from a source checkout.

### `readme`

Streams the `README.md` file to standard output for quick reference.

## Further help

Every command includes its own `--help` output generated by Typer. Combine the guidance above with the inline help text for the most up-to-date descriptions.
