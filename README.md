# Cloud Phone Pricing Intelligence Platform

**AI-powered competitive pricing monitoring and decision-support system** for UgPhone, VSPhone, Redfinger and LDCloud.

This repository evolves the original Cloud Phone Pricing Monitor into a complete pricing-intelligence project: Playwright collection, normalized product semantics, configuration matching, historical monitoring, a React Dashboard, deterministic pricing tools, evidence-grounded AI explanation and pricing What-if simulation.

**Repository:** `Nikolaustis/Cloud-Phone-Pricing-Monitor`  
**Live Dashboard:** https://nikolaustis.github.io/Cloud-Phone-Price-Dashboard-Site/  
**AI release line:** `v2.0.0-beta.1` → `v2.0.0`

> The numeric decision layer remains deterministic. An LLM may understand a question, choose tools and explain results, but it is not the authority for prices, medians, similarity scores, relative indexes or market-position thresholds.

## Core capabilities

- **Multi-platform Playwright collection** with local persisted authentication.
- **Normalized pricing semantics** for configuration, region, duration and purchase mode.
- **Historical intelligence**: current/previous/baseline price, carry-forward semantics and trend assets.
- **Comparable configuration matching** using Android, CPU, RAM, storage, region and duration evidence.
- **Pricing decision engine**: competitor median, UgPhone relative index, market position, alerts and reason codes.
- **React/Vite Dashboard** for overview, pairing, duration comparison, trends, changes and metrics.
- **AI Semantic Context** derived only from already-safe Dashboard data.
- **Ask Pricing Copilot** using deterministic query tools plus optional LLM orchestration.
- **AI Explain** with configuration/pairing evidence and data-origin caveats.
- **Pricing What-if** calculated in Python/JavaScript rules, never estimated by a model.
- **Evidence grounding** with stable `fact_id`, evidence IDs, data date and data revision.
- **AI Evaluation** covering routing, numeric exact match, grounding and correct abstention.
- **Public Evidence Mode** that works on GitHub Pages without exposing an API key.

## Architecture

```text
UgPhone / VSPhone / Redfinger / LDCloud
                 │
                 ▼
        Playwright collectors
                 │
                 ▼
Normalization / validation / history
                 │
                 ▼
Configuration matching + pricing rules
                 │
        ┌────────┴────────┐
        ▼                 ▼
 dashboard_data      AI Context Builder
        │                 │
        ▼                 ▼
 React Dashboard   dashboard_data/ai
        │            │            │
        │            │            └── Evidence Mode on GitHub Pages
        │            ▼
        │       FastAPI AI Service
        │            │
        │       deterministic tools
        │            │
        │       optional LLM provider
        └────────────┴──────────────► Pricing Intelligence Copilot
```

See:

- [Architecture](docs/ARCHITECTURE.md)
- [AI architecture](docs/AI_ARCHITECTURE.md)
- [Authentication design](docs/AUTHENTICATION_DESIGN.md)
- [AI evaluation](docs/AI_EVALUATION.md)
- [AI deployment](docs/AI_DEPLOYMENT.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [v2 release line](docs/V2_RELEASE.md)

## Windows quick start

### Base runtime

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

The canonical runtime is:

```text
<SkillRoot>\.venv\Scripts\python.exe
```

Collector login uses the local Playwright Chromium opened by `LOGIN.ps1`. ChatGPT Work / Cloud Browser authentication is not interchangeable with local collector state.

### Optional AI service dependencies

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_ai_dependencies_windows.ps1
```

The same optional layer can be installed with the base installer:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies -InstallAIDependencies
```

Build the safe semantic context:

```powershell
.\.venv\Scripts\python.exe -B .\build_ai_context.py
```

Start the optional FastAPI AI service:

```powershell
.\.venv\Scripts\python.exe -B .\run_ai_api.py
```

Default local endpoint:

```text
http://127.0.0.1:8787
```

## Dashboard AI modes

### Evidence Mode — public/demo default

If `VITE_AI_API_BASE_URL` is blank, the Dashboard Copilot reads static safe assets under:

```text
dashboard_data/ai/
```

It supports market brief, structured configuration queries, price changes, Explain, What-if and explicit abstention. No provider secret is required, so this mode is safe for GitHub Pages.

### LLM backend mode

The backend can optionally use an **operator-configured OpenAI-compatible chat-completions endpoint**. No vendor/model is hard-coded in the repository.

Backend-only environment variables:

```text
AI_ENABLE_LLM=1
AI_LLM_PROVIDER=openai_compatible
AI_LLM_ENDPOINT=...
AI_LLM_API_KEY=...
AI_LLM_MODEL=...
```

The frontend receives only `VITE_AI_API_BASE_URL`. Provider keys must never be placed in `VITE_*` variables or browser JavaScript.

## Deterministic AI tool layer

The service exposes a compact stable tool set:

```text
get_market_overview
search_configs
compare_configuration
get_pairing_evidence
get_price_changes
get_price_history
get_metric_definition
simulate_price
```

The intended flow is:

```text
user question
→ semantic/tool routing
→ deterministic query/calculation
→ compact evidence
→ optional LLM explanation
→ answer + evidence + data revision
```

This is intentionally not “send several MB of JSON to a chatbot”.

## AI context contract

`build_ai_context.py` derives an AI semantic layer from already-safe Dashboard exports:

```text
dashboard/public/dashboard_data/ai/
├── manifest.json
├── market_summary.json
├── config_index.json
├── price_events.json
├── pairing_index.json
├── trend_index.json
├── metric_dictionary.json
├── question_examples.json
└── market_brief.txt
```

Every normalized fact carries a stable `fact_id` where applicable. AI answers return evidence records plus `data_date` and `data_revision`, so a polished explanation cannot silently override the underlying structured data.

## Explainable pricing What-if

Example logic:

```text
proposed_price / competitor_median × 100
        ↓
new relative index
        ↓
new market position
```

Market-position thresholds remain deterministic:

```text
index < 90       → below_market
90–105           → competitive
>105–115         → slightly_high
>115              → high
```

The What-if tool holds competitor evidence constant at the current data revision and changes only the proposed UgPhone price.

## AI evaluation

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_AI_TESTS.ps1
```

The included synthetic demo benchmark currently contains **21 golden questions** and validates deterministic routing, evidence coverage, abstention and numeric retrieval. The generated `evals/demo_report.json` is explicitly a **tool-layer demo benchmark**, not a production LLM score.

Current synthetic deterministic benchmark generated by this package:

```text
Cases                 21
Intent accuracy       100%
Evidence coverage     100%
Abstention accuracy   100%
Numeric accuracy      100%
```

Do not put these numbers on a resume as production AI quality. For a real portfolio benchmark, evaluate safe real Dashboard rows and additionally report unsupported-claim rate, P50/P95 latency, provider/model revision and token/cost metrics.

## Demo dataset

`demo/dashboard_data/` is synthetic and contains no account/authentication information. `demo/ai_context/` is a prebuilt semantic context so recruiters or reviewers can exercise the AI layer without logging into cloud-phone platforms.

## Daily pipeline

The Windows updater is extended to:

```text
login preflight
→ collection
→ history rebuild
→ AI context build
→ Dashboard build
→ validation
→ optional GitHub Pages publish
```

The AI service is a separate read-only consumer of safe exported data. It cannot trigger collection, modify authentication, initialize a baseline or execute a purchase.

## Public/private boundary

Never publish:

```text
output/auth/
baselines/
.venv/
publisher.local.json
.env
AI provider keys
Playwright profiles/storage state
```

The GitHub Pages deployment repository should remain a static deployment target. Source code, AI backend, evaluation and Dashboard source belong in this main repository.

## Portfolio framing

See [PROJECT_PORTFOLIO.md](PROJECT_PORTFOLIO.md). The recommended project name on a resume is:

> **Cloud Phone Pricing Intelligence Platform｜AI 云手机竞品价格监测与定价决策平台**

## Disclaimer

This project is for price monitoring, data organization and business analysis. Use it in accordance with relevant website terms, account rules and applicable laws.

## Reproducible public runtime contract

The recommended release baseline remains explicit, but newer supported runtimes are not rejected merely for having a higher version:

```text
Recommended: Python 3.12.x + Node.js 22.x + Playwright 1.62.0
Supported:   Python 3.12.x / 3.13.x / 3.14.x
             Node.js 22.x / 24.x
```

A supported version is accepted only if dependency installation, tests, Chromium launch, AI/API contract and Dashboard build all pass. Python 3.14 compatibility uses `pandas==2.3.3`, which has CPython 3.14 wheels; `.python-version` and `.nvmrc` remain recommendations, not hard upper bounds.

The versions are recorded in `runtime-versions.json`, `.python-version` and `.nvmrc`. Direct Python dependencies are pinned; Dashboard dependencies are reproduced with `dashboard/package-lock.json` + `npm ci`.

A clean Windows machine is release-ready only after:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_V2.ps1 -Bootstrap
```

returns `RELEASE_READY=True`. The verifier launches Chromium, runs base/AI tests, rebuilds a synthetic safe dataset, starts a uniquely identified FastAPI process, verifies the expected `ai-context-v2` revision, builds the Dashboard and reproduces the public release Manifest.

### Local AI configuration

For optional LLM orchestration:

```powershell
Copy-Item .\ai.env.example .\ai.env
notepad .\ai.env
.\.venv\Scripts\python.exe .\run_ai_api.py
```

`ai.env` is loaded automatically by the backend; process environment variables take precedence. It is private, ignored by Git and rejected by the public release policy. Evidence Mode remains usable without any provider key.

### Git-tracked secret gate

CI validates the actual Git index with `tools/validate_git_tracked_files.py`. A committed `output/`, `baselines/`, authentication artifact, forbidden archive, private maintainer file or obvious credential token fails CI even if `.gitignore` or working-tree validation would otherwise hide it.

### Moving to another computer

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md). Public source, private historical/baseline data, authentication state and local publishing configuration are deliberately migrated through separate paths.

## License

This repository is released under the [MIT License](LICENSE).

### Maintainer-only live collector acceptance

Portable CI cannot prove third-party login sessions. Before claiming that the real collectors were revalidated on a machine with private credentials, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_REAL_COLLECTORS.ps1
```

This performs live auth preflight, the canonical four-platform collection, live AI-context rebuild and Dashboard build. A full pass emits `REAL_COLLECTOR_READY=True`. It is intentionally separate from public CI and from the credential-free synthetic demo gate.
