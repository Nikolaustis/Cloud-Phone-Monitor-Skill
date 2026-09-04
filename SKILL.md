# cloud-phone-pricing-intelligence

## Purpose

Use this skill for cloud-phone product/price monitoring and evidence-grounded pricing intelligence across UgPhone, VSPhone, Redfinger, and LDCloud.

The system has four analytical layers:

1. **Collection**: authenticated, non-purchasing price/data collection with local Playwright Chromium.
2. **Normalization and history**: stable product semantics, explicit collection states, baseline and historical price intelligence.
3. **Comparable pricing**: UgPhone-based configuration matching, competitor median, relative index and market-position logic.
4. **AI decision support**: a safe semantic context, deterministic query/calculation tools, evidence-grounded explanation and pricing What-if.

Do not compare platform package names alone. VIP/KVIP/SVIP/XVIP names are platform-specific and may represent different configuration tiers. AI must consume normalized configuration/duration evidence rather than infer comparability from names.

## When to use

Use this skill when the user asks for:

- 云手机基准价监测、竞品价格变化与历史趋势
- UgPhone 作为参照系的竞品比价
- VSPhone / Redfinger / LDCloud 价格变化
- 近似配置、质量调整价格、同购买周期比较、市场位置
- 活动价、涨跌、库存、地区、促销文案变化
- Dashboard 数据分析与可视化
- AI 市场简报 / Ask Pricing Copilot 自然语言查询
- “为什么被判定为 high / slightly_high”一类证据化解释
- Pricing What-if 调价模拟
- AI Evaluation / Benchmark / evidence-grounding 审计

## Safety and accuracy rules

1. Do not fabricate fields.
2. If a field is not visible in the page, DOM, or API response, leave it blank/null and record the uncertainty when necessary.
3. Never click a control that may create a purchase, order, payment, subscription, renewal, device instance, or confirmation.
4. If a page is blocked by login, CAPTCHA, region restriction, anti-bot checks, or JavaScript failure, preserve diagnostics and report the limitation.
5. Prefer structured API responses over DOM extraction when both provide the same product facts.
6. Do not split one product into multiple rows only because it supports multiple server regions; use `supported_server_regions`.
7. Treat `output/auth/`, cookies, tokens, account information, persistent browser profiles, and private baseline files as sensitive.
8. UgPhone and VSPhone must keep `purchase_mode` explicit:
   - `subscription`: auto-renew enabled
   - `non_subscription`: auto-renew disabled
9. Historical rows without `purchase_mode` are treated as subscription rows for backward compatibility.
10. VSPhone collection may change only the pricing-page auto-renew filter, must keep quantity at 1, read duration-card prices, ignore the footer order total, restore auto-renew when appropriate, and never click the final create/order button.
11. Authentication used by the local collector must originate from a local Playwright browser context. A ChatGPT Work / Cloud Browser session is isolated and must never be treated as a source for local collector cookies, storage state, persistent profiles, or runtime context.
12. For AI output, deterministic data/query tools are authoritative for numeric facts. An LLM may understand the question, select tools and explain returned facts, but must not invent or independently recalculate unsupported prices, medians, similarity scores, relative indexes, thresholds or dates.
13. AI answers must preserve `data_origin`, `analysis_status`, observation state and data revision. A `carry_forward` value is not a newly observed price.
14. If structured evidence is insufficient, the AI layer must abstain or state the limitation rather than infer a nonexistent SKU, configuration, time point or causal explanation.
15. AI provider credentials are backend-only secrets. Never place an API key in `VITE_*`, Dashboard JavaScript, static GitHub Pages assets, AI context JSON, logs or public release files.

## Authentication execution routing (hard rule)

Authentication-state tasks are **local-execution tasks**, not browser-navigation tasks. This routing rule takes precedence over general browsing behavior.

Trigger this route whenever the user asks to log in, sign in, save/record/refresh authentication state, repair an expired login, or continue after a login preflight failure for UgPhone, VSPhone, Redfinger, or LDCloud.

For these requests:

1. **NEVER** open the platform in ChatGPT Work / Cloud Browser for collector authentication.
2. **NEVER** ask the user to finish collector login inside a browser page opened by ChatGPT Cloud Browser.
3. **NEVER** attempt to read, export, copy, or convert Cloud Browser cookies/localStorage/sessionStorage into local collector auth files.
4. First determine whether a shell can execute against the user's **local Windows project/Skill filesystem**.
5. If local shell execution is available, start the two-stage local login controller:

   ```powershell
   .\LOGIN.ps1 <Platform> -Start
   ```

   Wait until the command reports `LOGIN_AGENT_STATE=WAITING_FOR_USER`. Then stop tool execution and tell the user to complete login in the newly opened local Chromium window and reply **“已完成”** in the chat.
6. When the user replies **“已完成”** in the context of an active login session, do not browse the web. Resume the same local authentication flow with:

   ```powershell
   .\LOGIN.ps1 <Platform> -Complete
   ```

   Treat `LOGIN_AGENT_STATE=SAVED_AND_VERIFIED` as success only when it belongs to the same active session.
7. If the local shell or local Skill filesystem is unavailable, **STOP**. Do not substitute Cloud Browser. Tell the user that collector authentication requires local execution and provide the exact `LOGIN.ps1` command instead.
8. If the user is operating PowerShell manually rather than through an agent, the interactive form remains valid:

   ```powershell
   .\LOGIN.ps1 <Platform>
   ```

9. `-Status` may inspect an active two-stage session; `-Cancel` may discard an abandoned session without deleting previously saved auth state.
10. If `-Start` returns success but no local Chromium window appears, or if `-Complete` reports that the active process identity/session no longer matches, treat that as a local execution/persistence failure. Do not fall back to Cloud Browser.

Expected protocol:

```text
user asks to record/refresh login state
        ↓
local shell: LOGIN.ps1 <Platform> -Start
        ↓
LOGIN_AGENT_STATE=WAITING_FOR_USER + session_id
        ↓
user logs in in LOCAL Chromium and replies “已完成”
        ↓
local shell: LOGIN.ps1 <Platform> -Complete
        ↓
session_id + PID/path/start-time validation
        ↓
post-save auth/business validation
        ↓
LOGIN_AGENT_STATE=SAVED_AND_VERIFIED
```

## Installation

From the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

For a new machine or missing Playwright runtime:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

Optional AI backend dependencies can be installed after the base `.venv` exists:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_ai_dependencies_windows.ps1
```

Or during installation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies -InstallAIDependencies
```

The installer is fail-fast: required source files are validated before copy and required installed files are validated again after copy. Missing `install_dependencies_windows.ps1`, `login_controller.py`, or other required files must fail installation rather than produce a partial Skill.

The installed Skill has one runtime authority: `<SkillRoot>\.venv\Scripts\python.exe`. `LOGIN.ps1`, scheduled collection and deployment verification must use that interpreter and must not silently fall back to PATH/system Python. Only `install_dependencies_windows.ps1` may discover a system Python, solely to create/repair `.venv`. The installer launch-tests Playwright Chromium; Google Chrome is not required.

Developer/test dependencies use the same dedicated runtime:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -c constraints-runtime.txt
.\RUN_TESTS.ps1
.\RUN_AI_TESTS.ps1
```

## Baseline workflow

Create or overwrite the default baseline after a verified collection:

```bash
python run.py --init-baseline
```

Daily/manual monitoring:

```bash
python run.py
```

Collect without same-product baseline comparison:

```bash
python run.py --skip-baseline-monitor
```

Skip the UgPhone quality-adjusted monitor:

```bash
python run.py --skip-quality-price-monitor
```

Use a custom quality-monitor configuration:

```bash
python run.py --quality-price-config path/to/config.json
```

## Login workflow

`LOGIN.ps1` is the Windows orchestration entrypoint. It launches `cloud_phone_monitor.login_controller`, which in turn launches the existing `cloud_phone_monitor.login_wait_for_signal` Playwright helper in a local headed Chromium process.

The controller/adapter use `LOGIN_PROTOCOL_VERSION = 4` as the session-state contract. The adapter discovers legacy helper CLI capability through `--help`, not by searching helper source text, so controller/helper revisions cannot drift silently. The controller adds these guarantees around the existing helper:

1. Every login attempt has a new `session_id`; stale historical `saved_and_verified` files cannot satisfy a new `-Complete`.
2. Process management is guarded by PID **plus executable path plus process start time** before signal/kill operations.
3. New storage state is first written to a session-specific `.pending.<session_id>` file and only atomically replaces the previous state after verification succeeds.
4. VSPhone, Redfinger, and LDCloud require positive authentication evidence plus purchase/business-page evidence after reopening the pending storage state; merely navigating to a URL is not `SAVED_AND_VERIFIED`.

Manual PowerShell login:

```powershell
.\LOGIN.ps1 UgPhone
.\LOGIN.ps1 VSPhone
.\LOGIN.ps1 Redfinger
.\LOGIN.ps1 LDCloud
```

Agent-controlled login:

```powershell
.\LOGIN.ps1 UgPhone -Start
# user logs in locally and replies “已完成”
.\LOGIN.ps1 UgPhone -Complete
```

The same pattern applies to the other platforms. `-Status` reports active-session integrity; `-Cancel` terminates only a process whose PID/path/start-time identity matches the stored session metadata.

UgPhone keeps the three-layer local authentication design:

```text
output/auth/ugphone_profile/                 # long-lived primary authentication authority
output/auth/ugphone_state.json               # Playwright-compatible storage state
output/auth/ugphone_runtime_context.json     # short-lived runtime bridge
```

For UgPhone, the existing helper continues to verify authenticated purchase-page business data and pricing API evidence, then reopens the persistent profile in headed and scheduled-task-equivalent headless modes. The controller commits the pending storage/runtime artifacts only after those helper checks succeed.

For VSPhone, Redfinger and LDCloud, the controller reopens the pending storage state headlessly and requires **server-acknowledged authentication evidence** together with platform purchase/business evidence. A token/cookie/storage key by itself is only a local credential hint and is not sufficient. Verification succeeds only when the page also exposes a strong authenticated UI marker (for example logout/sign-out), a user/account marker paired with credential evidence, or a successful user/profile/account API response containing non-empty identity fields. This is deliberately conservative: uncertainty fails closed rather than reporting a false `SAVED_AND_VERIFIED`.

The scheduled login preflight uses the same stronger non-UgPhone saved-state verifier, rather than checking only whether a JSON file exists.

`python run.py --headed` is a visible collection/debug mode, not the canonical first-login persistence workflow.

Saved login states and login-controller files must remain local under `output/auth/` and must not be uploaded or shared.

Public release tooling must be non-mutating with respect to staging validation: run release-facing Python with bytecode writes disabled (`-B` / `PYTHONDONTWRITEBYTECODE=1`), and reject any unexpected staging file before ZIP creation. `MANIFEST_SHA256.txt` must be regenerated from a clean explicit-allowlist staging tree and verified before upload.

## AI decision-support workflow

### Design principle

Do **not** send the complete raw Dashboard dataset to an LLM and ask it to calculate pricing results. The supported path is:

```text
user question
→ semantic/tool routing
→ deterministic query/calculation
→ compact evidence records
→ optional LLM explanation
→ answer + fact/evidence IDs + data date/revision
```

The semantic layer is built from already-safe Dashboard exports:

```powershell
.\.venv\Scripts\python.exe -B .\build_ai_context.py
```

It writes `dashboard/public/dashboard_data/ai/` with:

- `manifest.json`
- `market_summary.json`
- `config_index.json`
- `price_events.json`
- `pairing_index.json`
- `trend_index.json`
- `metric_dictionary.json`
- `question_examples.json`
- `market_brief.txt`

Each normalized fact receives a stable `fact_id` where applicable. The AI service and Dashboard expose these IDs as evidence instead of allowing prose to become its own source.

### Deterministic tool surface

Keep the public tool surface compact and stable:

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

`simulate_price` changes only the proposed UgPhone price while holding the current competitor evidence/revision fixed. Relative index and market-position classification are calculated by code, not by the language model.

### AI modes

The Dashboard supports two modes:

1. **Evidence Mode**: default public/GitHub Pages mode. It queries static safe AI context and requires no provider credential.
2. **LLM backend mode**: optional FastAPI service. A provider adapter may use an operator-configured OpenAI-compatible chat-completions endpoint, but no vendor/model/key is hard-coded into the repository.

Start the optional service with:

```powershell
.\.venv\Scripts\python.exe -B .\run_ai_api.py
```

Frontend code receives only `VITE_AI_API_BASE_URL`. Provider configuration stays in backend environment variables.

### Explain and What-if

`AI Explain` must return the deterministic pricing result first, then pairing/data-origin evidence, then optional interpretation. `Pricing What-if` must show old/new relative index and old/new market position from deterministic calculations.

### Evaluation

Run:

```powershell
.\RUN_AI_TESTS.ps1
```

The bundled demo benchmark is synthetic and validates tool-layer routing, evidence coverage, numeric retrieval and correct abstention. Do **not** report bundled demo scores as production LLM quality. Production portfolio metrics should be measured on a safe real-data benchmark and include numeric exact match, unsupported-claim rate, evidence coverage, abstention accuracy, latency and provider/model/data revision.

## Output

Each run creates a directory such as:

```text
output/cloud_phone_monitor_YYYYMMDD_HHMMSS/
```

Typical files:

- `products.csv`
- `products.xlsx`
- `products.jsonl`
- `product_brief.txt`
- `daily_changes.xlsx`
- `baseline_products_updated.xlsx`
- `quality_price_report.xlsx`
- `run_summary.json`
- `api_candidates.json`
- `page_artifacts/`

`quality_price_report.xlsx` contains:

- 配置配对建议
- 质量调整价格明细
- UG 相对竞品指数
- 变价合理性判断
- 指标说明

## Dashboard

The skill includes a local read-only Vite/React Dashboard under `dashboard/`.

```bash
cd dashboard
npm ci
npm run dev
```

The Dashboard is a business-facing price monitor, not a collection control panel. It must not expose controls that execute crawlers, modify login state, initialize a baseline, create purchases, or trigger subscriptions.

Main routes:

- `#/price-overview`
- `#/pairing`
- `#/duration-prices`
- `#/trends`
- `#/price-changes`
- `#/product-text`
- `#/metrics`

Historical Dashboard data can be rebuilt with:

```bash
python rebuild_dashboard_history.py --incremental
```

A full rebuild is reserved for recovery or migration cases:

```bash
python rebuild_dashboard_history.py --full
```

## Core duration buckets

Core comparison durations are:

```text
1 / 3 / 7 / 15 / 30 / 60 / 90 / 180 / 365 days
```

Other durations must be marked as non-core and excluded from the core same-duration comparison.

## Collection-state semantics

Do not equate a missing collection with a discontinued product.

Use explicit states for:

- current observed data
- temporarily missing collection
- unavailable
- discontinued
- not applicable
- unknown
- carry-forward from the last real observation

Ordinary short-term collection gaps may carry forward the most recent real observation to preserve time-series continuity. A product should only be treated as discontinued when there is sufficient evidence.

## Core metrics

- `current_price`: current transaction price
- `previous_price`: previous successful same-product same-duration price
- `baseline_price`: baseline price for the same product/duration
- `price_change_pct`: current price change versus previous price
- `seven_day_avg_price` / `thirty_day_avg_price`: historical averages with sample counts
- `config_similarity_score` / `comparability_level`: pairing quality
- `competitor_median_price`: same-duration median of strong/adjusted competitor prices
- `ugphone_relative_index`: UgPhone price / competitor median × 100
- `promotion_text_changed`: whether product/promotion text changed
- `reason_code`: explanation tag
- `alert_level`: `critical`, `warning`, `info`, or `none`

## Configuration pairing rules

UgPhone is the base platform.

Similarity considers:

- Android version
- CPU cores
- RAM
- Storage
- Supported server-region overlap
- Purchase-duration comparability

Levels:

- `strong_match`: score >= 90
- `adjusted_match`: 75 <= score < 90
- `weak_match`: 60 <= score < 75
- `not_comparable`: score < 60

Only `strong_match` and `adjusted_match` enter the core competitor median. `weak_match` is contextual evidence only.

## Expected workflow

1. Confirm dependencies are available.
2. When authentication is required or preflight reports missing/invalid state, apply **Authentication execution routing**. For agent-driven use, execute `LOGIN.ps1 <Platform> -Start`, wait for the user to reply “已完成”, then execute `LOGIN.ps1 <Platform> -Complete`. Never substitute Cloud Browser.
3. Run collection.
4. Review `run_summary.json`.
5. Review `products.xlsx` for product-table quality.
6. Review `daily_changes.xlsx` for same-product changes.
7. Review `quality_price_report.xlsx` for pairing, adjusted comparison and relative index.
8. Rebuild Dashboard history and run `build_ai_context.py` before Dashboard/AI publication.
9. Use deterministic AI tools for numerical query, Explain and What-if; attach fact/evidence IDs and data revision to AI answers.
10. Run the AI benchmark when changing semantic schemas, tools, routing or evidence behavior.
11. Rebuild/open the Dashboard when the user wants interactive review.
12. If a platform returns no valid records, inspect screenshots, HTML, API responses and blocked reasons.
13. Do not change scraper logic unless the currently collected evidence is genuinely insufficient.

## Redfinger price-SKU integrity

Redfinger price data is valid only when it comes from an authenticated price API or a visible card containing both a price and a purchase duration.

Game recommendations, wallet balances, navigation labels, loading skeletons, and plan-tab labels are diagnostic evidence only and must never become product-price records.

When no valid Redfinger price SKU is extracted, inspect the run diagnostics before using the resulting data for comparison.

## Privacy

Never publish or expose:

- `output/auth/`
- cookies or tokens
- account information
- private baseline workbooks
- persistent browser login profiles
- AI provider/API credentials
- backend `.env` files
- other sensitive runtime artifacts

## v2 public-readiness hardening

Canonical public verification additionally requires:

- Python 3.12.x + Node.js 22.x + Playwright 1.62.0 as the recommended baseline, with Python 3.13/3.14 and Node.js 24 admitted only when the complete compatibility gates pass;
- destructive demo output guarded to controlled runtime/temp directories only;
- Git-tracked files validated independently of `.gitignore`;
- FastAPI readiness bound to the current process PID, per-launch token and expected AI data revision;
- optional provider configuration loaded from private `ai.env` without exposing secrets to Vite/frontend source;
- migration of private history/baseline/local config handled separately from public source.
