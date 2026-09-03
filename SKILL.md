# cloud-phone-baseline-price-monitor

## Purpose

Use this skill when the user needs cloud phone product and price monitoring for UgPhone, VSPhone, Redfinger, and LDCloud.

The workflow has two main analytical layers:

1. Same-product baseline monitoring: compare current product rows against a private baseline workbook.
2. UgPhone-based comparable configuration monitoring: pair nearby competitor configurations, normalize purchase durations, apply rule-based quality adjustment, and compare market position.

Do not compare platform package names alone. VIP/KVIP/SVIP/XVIP names are platform-specific and may represent different configuration tiers.

## When to use

Use this skill when the user asks for:

- 云手机基准价监测
- UgPhone 作为参照系的竞品比价
- VSPhone / Redfinger / LDCloud 价格变化
- 近似配置、质量调整价格、同购买周期比较
- 活动价、涨跌、库存、地区、促销文案变化
- 云手机产品价格趋势与市场位置分析

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

## Installation

From the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

For first-time dependency installation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

Manual Python dependencies:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
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

The canonical login entry point is the local PowerShell wrapper:

```powershell
.\LOGIN.ps1 UgPhone
.\LOGIN.ps1 VSPhone
.\LOGIN.ps1 Redfinger
.\LOGIN.ps1 LDCloud
```

`LOGIN.ps1` launches the existing `cloud_phone_monitor.login_wait_for_signal` helper in a local headed Playwright Chromium process, waits until that browser is ready, asks the user to complete the login there, creates the local signal after Enter is pressed, then waits for the Python helper to validate and persist the state.

Do not complete collector authentication in ChatGPT Work / Cloud Browser. Its Cookie, localStorage and sessionStorage data are isolated from the local project and cannot become `output/auth/` state.

UgPhone keeps the existing three-layer local authentication design:

```text
output/auth/ugphone_profile/                 # long-lived primary authentication authority
output/auth/ugphone_state.json               # Playwright-compatible storage state
output/auth/ugphone_runtime_context.json     # short-lived runtime bridge
```

For UgPhone, the login helper verifies authenticated purchase-page business data and pricing API evidence before saving, then reopens the persistent profile in headed and scheduled-task-equivalent headless modes. The runtime snapshot is only a short-lived fill-missing bridge and must not override newer state already present in the persistent profile.

VSPhone, Redfinger and LDCloud use the same `LOGIN.ps1` user entry point and save platform-specific Playwright storage state. Their current platform-specific live-auth verification is less strict than UgPhone, so do not describe those three as having the same purchase/API-level proof unless their verifier is strengthened later.

`python run.py --headed` is a visible collection/debug mode, not the canonical first-login persistence workflow.

Saved login states must remain local under `output/auth/` and must not be uploaded or shared.

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
2. When authentication is required or preflight reports missing/invalid state, run the corresponding local `LOGIN.ps1 <Platform>` flow and complete login only in the Playwright Chromium window it opens.
3. Run collection.
4. Review `run_summary.json`.
5. Review `products.xlsx` for product-table quality.
6. Review `daily_changes.xlsx` for same-product changes.
7. Review `quality_price_report.xlsx` for pairing, adjusted comparison and relative index.
8. Rebuild/open the Dashboard when the user wants interactive review.
9. If a platform returns no valid records, inspect screenshots, HTML, API responses and blocked reasons.
10. Do not change scraper logic unless the currently collected evidence is genuinely insufficient.

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
- other sensitive runtime artifacts
