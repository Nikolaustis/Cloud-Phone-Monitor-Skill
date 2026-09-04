# Contributing

## Engineering rules

1. Keep runtime/private data outside public source and release staging.
2. Do not weaken authentication verification or profile locking to make a failing login appear successful.
3. Do not add purchase/order/payment/subscription confirmation actions to collectors, Dashboard or AI tools.
4. Keep controller/helper protocol changes synchronized and behavior-tested.
5. Use canonical `run.py` so UgPhone profile locking remains enforced.
6. Treat deterministic pricing tools as authoritative for numeric AI output; LLM/provider code must not duplicate business calculations.
7. Preserve `fact_id`, data revision, observation/data-origin semantics and explicit abstention behavior when changing the AI context or tools.
8. Never place provider secrets in Dashboard/Vite source. The only frontend AI configuration is the backend base URL.
9. Keep the public AI tool surface compact and schema-stable; incompatible changes require tests and a release-note entry.

## Before submitting changes

On Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_dependencies_windows.ps1 -InstallDevDependencies
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_ai_dependencies_windows.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_TESTS.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_AI_TESTS.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PREPARE_RELEASE.ps1
```

`PREPARE_RELEASE.ps1` is the public boundary. It builds an allowlist-only staging tree, validates the tree and Manifest, and creates the canonical deterministic release ZIP. Do not publish the developer working tree merely because `.gitignore` exists.

When reporting AI quality, distinguish the bundled synthetic deterministic benchmark from a production LLM benchmark. Resume/README production metrics must state the data revision and provider/model used.

## Public-readiness rules

- Keep the recommended CI baseline aligned with `runtime-versions.json` (Python 3.12.x / Node 22.x / Playwright 1.62.0) and keep compatibility jobs green for Python 3.13/3.14 and Node 24.
- Never weaken `tools/validate_git_tracked_files.py` to make a committed private/runtime file pass.
- Demo helpers that delete directories must call the central output-path guard first.
- API smoke tests must bind health to the PID, launch token and data revision created by the current test run; HTTP 200 alone is not sufficient.
- `ai.env` is local-only. Add public examples to `ai.env.example` instead.
