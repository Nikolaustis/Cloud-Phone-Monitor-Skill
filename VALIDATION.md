# Validation

## Base runtime

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_TESTS.ps1
```

Expected coverage includes authentication/session contracts, profile locking, release policy, collector/data behavior and Windows PowerShell smoke tests.

## AI layer

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_AI_TESTS.ps1
```

The AI test layer verifies:

- `ai-context-v2` normalization and stable fact IDs;
- deterministic query/compare/pairing/history/What-if tools;
- explicit abstention for unsupported entities;
- Dashboard Copilot integration and absence of provider credentials in frontend source;
- bundled synthetic benchmark routing, evidence and numeric retrieval.

The bundled benchmark is not a production LLM quality claim.

## Manual AI context check

```powershell
.\.venv\Scripts\python.exe -B .\build_ai_context.py --data-dir .\demo\dashboard_data --output-dir .\demo\ai_context
.\.venv\Scripts\python.exe -B .\evals\run_eval.py
```

`demo/ai_context/manifest.json` must report `schema_version = ai-context-v2`.

## Optional API contract

After installing `requirements-ai.txt`:

```powershell
.\.venv\Scripts\python.exe -B -c "from ai_backend.app import app; print(app.title, app.version)"
```

The service version for this beta line is `2.0.0-beta.1`.

## Release contract

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PREPARE_RELEASE.ps1
```

Only a clean staging tree with a regenerated and revalidated `MANIFEST_SHA256.txt` should be used as the GitHub public-release baseline.

## Git-tracked public-tree gate

`.gitignore` is not a security boundary. Before public upload, CI runs:

```bash
python -B tools/validate_git_tracked_files.py .
```

against `git ls-files`. This rejects tracked files outside the canonical public allowlist and scans tracked text for conservative credential patterns. A simulated tracked `output/auth/*` file or obvious token must fail the test suite.

## Service identity gate

FastAPI `/health` exposes an ephemeral launch token, service PID, instance id and AI data revision. `START_DEMO.ps1` and `VERIFY_V2.ps1` require all of them to match the process and context started by the current run. An already occupied port or stale API process is therefore a hard failure rather than a false PASS.

## Runtime versions

The release gate accepts CPython 3.12-3.14 and Node.js 22 or 24, while Python 3.12 + Node 22 remains the recommended baseline. Every accepted runtime must still pass pinned dependency installation, Playwright 1.62.0 Chromium launch, tests, AI/API contract and Dashboard build. See `runtime-versions.json`.

## Real collector acceptance

`VERIFY_REAL_COLLECTORS.ps1` is a maintainer-only gate that requires private platform login state. It verifies live auth, collects all four platforms, checks that each platform produced records, rebuilds the AI context and rebuilds the Dashboard. This is the evidence required to say the live collector path was revalidated; public CI does not and should not possess these credentials.

### Demo runtime deletion safety

`tools/prepare_demo_runtime.py` refuses the repository root, its ancestors, arbitrary source subtrees, the OS/CI temp root itself, and any pre-existing external temp directory that does not carry this project's `demo-runtime-v1` ownership marker. This prevents a typo from turning demo cleanup into a broad recursive delete.
