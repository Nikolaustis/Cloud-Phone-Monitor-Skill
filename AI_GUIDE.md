# Cloud Phone Pricing Intelligence Skill — AI Guide

## Design principle

**Numbers are computed by deterministic tools. Models interpret questions, select tools and explain evidence.**

The AI subsystem never reads `output/auth/`, browser profiles, cookies or private baselines. It consumes the already-safe Dashboard semantic export only.

## Build context

```powershell
.\.venv\Scripts\python.exe -B .\build_ai_context.py
```

The output is `dashboard/public/dashboard_data/ai/` and is copied into the static Dashboard build by Vite.

## Evidence Mode

Leave `VITE_AI_API_BASE_URL` blank. The React Copilot loads static AI context and provides deterministic brief/query/explain/what-if behavior with no backend key.

## AI service

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_ai_dependencies_windows.ps1
.\.venv\Scripts\python.exe -B .\run_ai_api.py
```

Endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | context revision + AI mode |
| `GET /api/ai/brief` | deterministic market brief |
| `POST /api/ai/ask` | tool-grounded query |
| `POST /api/ai/explain` | deterministic explanation + pairing evidence |
| `POST /api/ai/what-if` | deterministic proposed-price simulation |
| `GET /api/ai/configs` | normalized comparable configs |
| `GET /api/ai/tools` | tool catalog |
| `POST /api/ai/refresh` | refresh context cache |

## Optional LLM provider

The service defaults to Evidence Mode. To enable an LLM, configure a backend-only compatible endpoint through `ai.env.example`.

The provider is isolated behind `ai_backend/providers/`; business logic does not import a vendor SDK. This allows the model/provider to change without rewriting pricing tools.

## Safety boundary

- No API key in Vite/frontend variables.
- Rate limit is enforced on `/api/ai/*`.
- Input length and tool rounds are bounded.
- The LLM cannot call collector/login/purchase actions.
- Carry-forward and missing data must preserve their observation state.
- Missing configuration → abstain, not guess.

## Evaluation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_AI_TESTS.ps1
```

Evaluation is split conceptually into:

1. tool routing;
2. numeric correctness;
3. evidence grounding;
4. abstention;
5. answer quality/latency/cost when an LLM is enabled.

## Local `ai.env`

Copy `ai.env.example` to `ai.env` for optional provider configuration. The backend loads `ai.env` automatically and gives process environment variables higher precedence. `ai.env` is never part of a public staging tree.

## API readiness semantics

A valid demo/release health check requires more than HTTP success. The verifier matches `ok=true`, API version, `ai-context-v2`, `safe_data_only=true`, the expected `data_revision`, the spawned process PID and a per-launch random token. This prevents a stale process on the same port from satisfying the release gate.
