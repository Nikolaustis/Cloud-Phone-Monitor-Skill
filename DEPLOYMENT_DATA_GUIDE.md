# Data and Privacy Guide

This document defines the local/private boundary for Cloud Phone Pricing Intelligence Platform.

## Local runtime data

Runtime collection and generated artifacts live under `output/` and are not public source. Authentication material lives under `output/auth/` and may include Playwright storage state, cookies, runtime context, login control/status files and Chromium persistent profiles.

Collector authentication must be created by the **local Playwright Chromium** launched by this project. Remote/Cloud Browser state is not interchangeable with local collector authentication.

## Baselines and history

Private business baselines and operational history should remain outside the public repository. Typical local paths include `baselines/`, `output/latest/` and incremental history caches under `output/`.

## Local publishing configuration

Public source contains only `publisher.local.example.json`. Copy it locally to:

```text
publisher.local.json
```

That file is gitignored. Repository URLs, local clone paths, branches and commit messages are operator configuration rather than public release state. If publishing is not configured, collection/build/validation remain local-only.

`PUBLISH_PUBLIC_SOURCE.ps1` publishes only a freshly rebuilt explicit-allowlist public staging tree. It does not mirror the developer working tree.

## Demo runtime

`START_DEMO.ps1` prepares synthetic demo material under:

```text
output/demo_runtime/
```

The demo is isolated from real `dashboard/public/dashboard_data` and does not require platform credentials or provider secrets.

## Generated Dashboard files

Generated/dependency directories such as `dashboard/dist/`, `dashboard/node_modules/` and `dashboard/public/dashboard_data/` are not core public source. The public repository ships a separate synthetic dataset under `demo/` for reproducible evaluation.

## Never publish

- cookies, tokens, passwords or account details;
- Playwright storage state or persistent browser profiles;
- login signal/status/control logs;
- private baselines or raw operational history;
- `publisher.local.json`;
- backend `.env` files or AI provider API keys;
- unsanitized API responses/diagnostics;
- `.venv`, Playwright browser binaries, `node_modules`, build output or runtime logs.

## AI local environment file

Optional AI provider configuration is stored in:

```text
ai.env
```

Create it from `ai.env.example`. The backend reads it automatically, while process environment variables take precedence. `ai.env` is private and is excluded/rejected by Git/public release validation.

## Migration boundary

For a computer migration, keep public source and private state separate. `output/`, `baselines/`, `publisher.local.json` and `ai.env` may be copied only through private storage as needed. Authentication material under `output/auth/` should preferably be recreated with local Playwright login on the new machine. See `MIGRATION_GUIDE.md`.
