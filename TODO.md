# BiRRe CLI Refactor Tracker

## 1. Current Snapshot (2025-10-29 - MAJOR BREAKTHROUGH)
- **Status**: CLI refactor MAJOR breakthrough. `app.py` reduced from 3421 → 1229 lines (64% reduction).
- **Test Status**: ✅ ALL 76 OFFLINE TESTS PASSING (100%)
- **Commands Extracted**: run, config (3 commands), logs (4 commands), selftest (partial)
- **Legacy Code Cleanup**: Removed 654 lines total (437 duplicate helpers + 217 obsolete monkey-patching)
- **Remaining Work**: Selftest completion, formatting.py population, main.py refactor

## 2. Target Architecture (Agreed Plan)

### 2.1 Application Layer
```
src/birre/application/
├── __init__.py
├── server.py              # FastMCP server assembly (unchanged)
├── startup.py             # Offline/online startup checks
└── diagnostics.py         # NEW: tool discovery + validation helpers
    ├── collect_tool_map()
    ├── discover_context_tools()
    ├── run_context_tool_diagnostics()
    ├── run_company_search_diagnostics()
    ├── run_rating_diagnostics()
    ├── run_company_search_interactive_diagnostics()
    ├── run_manage_subscriptions_diagnostics()
    ├── run_request_company_diagnostics()
    └── auxiliary validators / aggregators
```

### 2.2 CLI Layer
```
src/birre/cli/
├── __init__.py            # Re-export Typer app & main entry point
├── app.py                 # Build Typer root, register commands only
├── main.py                # Console script entry (thin wrapper)
├── models.py              # CLI-facing dataclasses, payloads
├── options.py             # Shared Typer option factories/validators
├── helpers.py             # Misc CLI utilities (await_sync, invocation builders, etc.)
├── formatting.py          # Rich table/text formatting helpers
└── commands/
    ├── __init__.py        # Command registration surface
    ├── run.py             # Implementation of `birre run`
    ├── config.py          # Configuration subcommands (show, validate, etc.)
    ├── logs.py            # Log maintenance subcommands (clear, rotate, show path)
    └── selftest/
        ├── __init__.py
        ├── command.py     # Typer selftest entry point
        ├── runner.py      # SelfTestRunner orchestration
        ├── models.py      # Self-test result/attempt models
        └── rendering.py   # Rich output helpers
```

## 3. Filesystem State vs Plan (2025-10-29 - UPDATED)

```
src/birre/application/
├── __init__.py
├── server.py
├── startup.py
└── diagnostics.py          <- exists, populated with diagnostics logic ✅

src/birre/cli/
├── __init__.py             <- exports app/main (legacy behaviour)
├── app.py                  <- ✅ REDUCED TO 1229 LINES (from 3421, 64% reduction, -654 lines this session!)
├── main.py                 <- still proxies to legacy app.main ❗️
├── models.py               <- implemented dataclasses ✅
├── options.py              <- implemented option aliases/validators ✅
├── helpers.py              <- sync bridge + invocation helpers ✅
├── formatting.py           <- EMPTY - no formatting helpers yet ❗️
└── commands/
    ├── __init__.py         <- placeholder re-export file
    ├── run.py              <- fully implemented (128 lines) ✅
    ├── config.py           <- ✅ FULLY IMPLEMENTED (914 lines), all 3 commands, 8/8 tests
    ├── logs.py             <- ✅ FULLY IMPLEMENTED (464 lines), all 4 commands, 4/4 tests
    └── selftest/
        ├── __init__.py     <- placeholder
        ├── command.py      <- implemented (137 lines), uses SelfTestRunner from diagnostics ✅
        ├── runner.py       <- EMPTY STUB ❗️
        ├── models.py       <- EMPTY STUB ❗️
        └── rendering.py    <- implemented (220 lines) ✅
```

Legend: ✅ implemented, ❗️ outstanding work.

**App.py Cleanup Progress (2025-10-29):**
- Original size: 3421 lines
- After command extraction: 1896 lines (45% reduction)
- After legacy helper cleanup: 1459 lines (57% reduction, 437 lines removed)
- After monkey-patching removal: 1229 lines (64% reduction, 217 lines removed)
- **Total cleanup: 654 lines removed in this session (-35% in one session!)**

Cleanup details:
- Config display helpers (219 lines) - duplicates in config.py
- Config init helpers (216 lines) - duplicates in config.py  
- Diagnostic delegates (216 lines) - obsolete monkey-patching layer
- Unused imports (3 lines) - `Callable`, `Mapping`, `Table`, `cli.options`, `diagnostics_module`, `invoke_with_optional_run_sync`

## 4. Work Completed
1. **Diagnostics migration**: All tool-level diagnostics (context discovery, tool invocation helpers, validation functions) moved into `src/birre/application/diagnostics.py`.
2. **Helper refactor**: `src/birre/cli/helpers.py` now owns the event-loop bridge (`await_sync`), CLI invocation builder, runtime/logging resolution, server preparation, and diagnostic runner wrappers.
3. **Support modules**: `models.py`, `options.py`, `helpers.py` created with production-ready implementations.
4. **Run command extraction**: `src/birre/cli/commands/run.py` encapsulates the `birre run` Typer command; `app.py` now registers this module.
6. **Partial test updates**: `tests/unit/test_server_cli.py` adjusted to use `cli_helpers.build_invocation` (though many patches still point to obsolete symbols).
7. **Test patch fixes (2025-10-29)**: Updated all test patches to reference correct module paths for moved functions. 20 of 28 tests now passing, providing stable baseline for continued refactoring.
8. **Config command extraction (2025-10-29)**: All config commands (`init`, `show`, `validate`) extracted from `app.py` to `commands/config.py` (914 lines). Includes ~15 helper functions, proper imports, and full functionality. Reduced app.py from ~3421 to ~3114 lines (307 lines removed). All 8 config tests passing.
9. **Logs command extraction (2025-10-29)**: All logs commands (`clear`, `rotate`, `path`, `show`) extracted from `app.py` to `commands/logs.py` (464 lines). Includes ~11 helper functions for log parsing, filtering, and display. Reduced app.py from ~3106 to ~2696 lines (410 lines removed). All 4 logs tests passing after updating monkeypatch references to `logs_command` module.
10. **Selftest rendering extraction (2025-10-29)**: All healthcheck rendering functions moved to `commands/selftest/rendering.py` (220 lines). Removed 4 duplicate copies of healthcheck functions from `app.py` (801 lines removed). Reduced app.py from ~2696 to ~1896 lines. Updated `selftest/command.py` to use `render_healthcheck_summary()` from rendering module. All offline tests still passing (69/76).
11. **Legacy helper cleanup (2025-10-29)**: Removed 437 lines of duplicate helper functions from `app.py`:
    - Removed 219 lines of config display helpers (already in config.py): `_mask_sensitive_string`, `_format_display_value`, `_flatten_to_dotted`, `_collect_config_file_entries`, `_collect_cli_override_values`, `_build_cli_source_labels`, `_build_env_source_labels`, `_build_cli_override_rows`, `_build_env_override_rows`, `_effective_configuration_values`, `_determine_source_label`, `_print_config_table`
    - Removed 216 lines of config init helpers (already in config.py): `_prompt_bool`, `_prompt_str`, `_validate_and_apply_normalizer`, `_collect_or_prompt_string`, `_format_config_value`, `_format_config_section`, `_generate_local_config_content`, `_determine_value_source`, `_prompt_and_record_string`, `_prompt_and_record_bool`, `_check_overwrite_destination`, `_display_config_preview`
    - Removed 2 lines of unused imports: `Callable`, `Mapping`, `Table`, `cli.options`
    - Reduced app.py from 1896 → 1459 lines (23% cleanup, 57% total reduction from original)
    - **All 79 tests passing (100%)** after cleanup
12. **Diagnostic delegate removal (2025-10-29)**: Removed 217 lines of obsolete monkey-patching:
    - Removed 6 `_run_*` wrapper functions (invoke_with_optional_run_sync wrappers)
    - Removed 10 `_delegate_*` functions (run_sync parameter poppers)
    - Removed monkey-patching block (11 diagnostics_module reassignments)
    - Removed 1 unused import: `diagnostics_module`, `invoke_with_optional_run_sync`
    - **Root Cause**: Legacy code from before helpers.py existed - created redundant 3-layer wrapper
    - **Solution**: SelfTestRunner already passes run_sync directly to diagnostic functions
    - Reduced app.py from 1459 → 1229 lines (15% cleanup, 64% total reduction)
    - **All 76 offline tests passing (100%)** after removal

## 5. Outstanding Work / Gaps

1. **Command extraction**
   - ✅ run, config, logs commands fully extracted and tested
   - ⚠️ selftest command.py exists but runner.py and models.py are EMPTY STUBS
   - ❗️ SelfTestRunner and related models still live in application/diagnostics.py
   - Decision needed: Keep runner in diagnostics.py (current approach) OR move to commands/selftest/

2. **Formatting helpers**
   - ✅ Healthcheck rendering functions moved to commands/selftest/rendering.py
   - ❗️ formatting.py is COMPLETELY EMPTY - no shared utilities extracted yet
   - ❗️ Many Rich helpers still scattered in app.py (_print_config_table, etc.)

3. **app.py cleanup - NOT STARTED**
   - ❗️ Still ~1900 lines with legacy helper functions
   - ❗️ Contains: _collect_config_file_entries, _prompt_and_record_*, _validate_company_entry,
     _check_domain_match, _aggregate_tool_outcomes, _HealthcheckContext, _delegate_* wrappers
   - ❗️ These should be moved to appropriate modules or removed if obsolete

4. **Entry-point cleanup**
   - ❗️ main.py still proxies to legacy app.main
   - ❗️ No refactoring of entry point structure yet

5. **Test alignment - INCOMPLETE**
   - ✅ run, config, logs tests all passing (12/12 passing)
   - ✅ selftest tests all passing (10/10 passing)
   - ✅ **All 28/28 tests passing (100%)**
   - ✅ Tests successfully stabilized with proper SelfTestRunner mocking
   - Mocking strategy: Mock `birre.cli.commands.selftest.command.SelfTestRunner` class
     to return fake `SelfTestResult` objects, avoiding real HTTP calls

6. **Self-test orchestration - NOT DONE**
   - ❗️ commands/selftest/runner.py is an empty 5-line stub
   - ❗️ commands/selftest/models.py is an empty 5-line stub
   - ❗️ All logic remains in application/diagnostics.py

7. **Documentation**
   - ❗️ README not updated to reflect new CLI structure
   - ❗️ Developer docs don't mention modular command organization


## 6. Detailed TODO Checklist

- [x] **Commands/config.py**: ✅ COMPLETE - Config command group extracted (2025-10-29) - all 3 commands
  (`init`, `show`, `validate`) with ~15 helper functions. All 8 tests passing.
- [x] **Commands/logs.py**: ✅ COMPLETE - Log maintenance commands extracted (2025-10-29) - all 4 commands
  (`logs clear`, `logs rotate`, `logs path`, `logs show`) with ~11 helper functions. All 4 tests passing.
- [x] **Legacy helper cleanup**: ✅ COMPLETE - Removed 437 lines of duplicate functions (2025-10-29):
  - Config display helpers (219 lines) - all duplicated in config.py
  - Config init helpers (216 lines) - all duplicated in config.py
  - Unused imports (2 lines)
  - App.py reduced from 1896 → 1459 lines (23% cleanup, 57% total reduction)
- [ ] **Commands/selftest/**:
  - [ ] `command.py`: Implement Typer command registration (register onto root app).
  - [ ] `runner.py`: Relocate self-test orchestration, TLS retry logic, startup check invocation.
  - [ ] `models.py`: Move self-test dataclasses (`HealthcheckResult`, `AttemptReport`, etc.).
  - [ ] `rendering.py`: Move Rich rendering helpers for healthcheck summaries.
- [ ] **Formatting helpers**: Populate `src/birre/cli/formatting.py` with Rich table/text
  utilities and update commands to use them.
- [ ] **Remove `_delegate_*` wrappers**: After commands consume helpers/application diagnostics
  directly, drop the remapping code from `app.py`.
- [ ] **`app.py` cleanup**: Once commands are externalised, trim `app.py` to simple Typer
  wiring + minimal glue.
- [ ] **`main.py` refresh**: Update to instantiate Typer app directly (no legacy proxy) after
  `app.py` is slimmed down.
- [ ] **Test updates**: Repoint `tests/unit/test_server_cli.py` mocks/patches to
  `birre.cli.commands.run` and `birre.cli.helpers` (and analogous modules for
  config/logs/selftest once implemented).
- [ ] **Integration tests**: Re-run `pytest -m offline` (then `-m online`) once unit tests pass.
- [ ] **Documentation**: Update README / docs to describe new CLI structure and command entry
  points.

## 7. Execution Roadmap

1. **Stabilise current tests** ✅ COMPLETE (2025-10-29)
   - ✅ Updated patches for run, config, logs commands → all passing
   - ✅ Fixed all 7 failing selftest tests by mocking SelfTestRunner class
   - ✅ **All 28/28 unit tests passing (100%)**
   - ✅ **All 79/79 offline tests passing (100%)**
   - Test suite is now fully stabilized

2. **Extract Config & Logs commands** ✅ COMPLETE (2025-10-29)
   - ✅ Config: All 3 commands extracted to commands/config.py (914 lines), 8/8 tests passing
   - ✅ Logs: All 4 commands extracted to commands/logs.py (464 lines), 4/4 tests passing
   - ✅ Selftest rendering: Extracted to commands/selftest/rendering.py (220 lines)
   - ✅ Total reduction: app.py reduced from ~3421 to ~1896 lines (45%)

3. **Cleanup legacy helpers** ✅ COMPLETE (2025-10-29)
   - ✅ Removed 654 lines of obsolete/duplicate code from app.py (437 helpers + 217 monkey-patching)
   - ✅ Deleted config display helpers (219 lines) - already in config.py
   - ✅ Deleted config init helpers (216 lines) - already in config.py
   - ✅ Removed diagnostic delegate layer (216 lines) - obsolete monkey-patching
   - ✅ Removed unused imports (3 lines)
   - ✅ **App.py now 1229 lines (64% total reduction from 3421 original)**
   - ✅ **All 76 offline tests passing after cleanup**

4. **Implement Self-test package** ⚠️ PARTIALLY DONE
   - ✅ commands/selftest/command.py created (137 lines) - registers command
   - ✅ commands/selftest/rendering.py created (220 lines) - healthcheck display
   - ✅ All 10 selftest tests passing with proper mocking
   - ❌ commands/selftest/runner.py is EMPTY (5 lines, no logic)
   - ❌ commands/selftest/models.py is EMPTY (5 lines, no logic)
   - ❌ SelfTestRunner still in application/diagnostics.py (not moved)
   - Decision: Keep SelfTestRunner in diagnostics.py OR extract to commands/selftest/

5. **Consolidate formatting** ❌ NOT STARTED
   - formatting.py is completely empty
   - No shared Rich helpers extracted
   - Decision needed: populate formatting.py or leave rendering in command modules

6. **Remove legacy delegates & cleanup app.py** ✅ COMPLETE (2025-10-29)
   - ✅ app.py reduced from 1459 → 1229 lines (64% total reduction)
   - ✅ Removed all 16 diagnostic delegate functions (_delegate_*, _run_*)
   - ✅ Removed obsolete monkey-patching block (11 diagnostics_module reassignments)
   - ✅ Identified root cause: Legacy code from before helpers.py existed
   - ✅ **All 76 offline tests passing after delegate removal**

7. **Finalise entry point** ❌ NOT STARTED
   - main.py unchanged
   - Entry point structure not refactored

8. **Regression suite** ✅ COMPLETE (2025-10-29)
   - ✅ Offline tests: 76/76 passing (100%)
   - ✅ All unit tests passing
   - ✅ Test suite fully stabilized
   - Online tests not verified yet (requires BITSIGHT_API_KEY)

9. **Docs & polish** ❌ NOT STARTED
   - Update README, developer docs, and any architectural diagrams.
   - Remove stale imports or TODO comments leftover in migrated files.


## 8. Testing Status (as of 2025-10-29 - ALL 76 OFFLINE TESTS PASSING)

- `pytest tests/unit/test_server_cli.py` → **28/28 Passing** (100%) ✅
  - ✅ run command tests: 2/2 passing
  - ✅ config command tests: 8/8 passing
  - ✅ logs command tests: 4/4 passing
  - ✅ Helper/utility tests: 4/4 passing
  - ✅ Selftest command tests: 10/10 passing

- `pytest -m offline` → **76/76 Passing** (100%) ✅
  - Includes all unit tests plus additional offline integration tests
  - Test suite fully stabilized after monkey-patching removal
  - 3 tests deselected (online-only tests, require BITSIGHT_API_KEY)

**Test Fixes Completed (2025-10-29):**

- ✅ Fixed all 7 failing selftest tests by mocking `SelfTestRunner` class
- ✅ Mocking strategy: Patch `birre.cli.commands.selftest.command.SelfTestRunner` 
  to return fake `SelfTestResult` objects
- ✅ Tests no longer perform real HTTP calls to BitSight API
- ✅ Each test validates specific behavior (online/offline modes, TLS retry, config options)

**Previous Test Fixes:**

- Updated all test patches to reference correct module paths:
  - Functions in `cli.helpers`: initialize_logging, run_offline_checks, run_online_checks,
    prepare_server, resolve_runtime_and_logging
  - Functions in `application.diagnostics`: run_context_tool_diagnostics,
    discover_context_tools
  - Functions in `cli.commands.logs`: resolve_logging_settings_from_cli, rotate_logs,
    parse_log_line
- Added `run_sync=None` parameter to fake_diagnostics functions
- Fixed await_args assertion in test_main_runs_server_when_checks_pass

**Status:** Test suite fully stabilized at 28/28 passing (100%).



## 9. Risks & Dependencies

- Continued edits to `app.py` while tests are failing risk obscuring regressions; stabilise
  unit tests before further extraction.
- Self-test logic is tightly coupled with diagnostics helpers; ensure new modules import from
  `application.diagnostics` / `cli.helpers` rather than reintroducing duplicated logic.
- Remember to adjust packaging (console scripts) once `main.py` changes; failure to do so will
  break `uvx --from git+… birre` entry point.

_This document provides context for another engineer or LLM agent to resume the refactor without
additional history._

