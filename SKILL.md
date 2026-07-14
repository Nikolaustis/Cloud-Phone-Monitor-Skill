# cloud-phone-baseline-price-monitor

## Purpose

Use this skill when the user needs cloud phone product and price monitoring for UgPhone, VSPhone, Redfinger, and LDCloud.

The workflow now does two things:

1. Same-product baseline monitoring: compare current product rows against a private baseline workbook.
2. UgPhone-based comparable configuration monitoring: pair nearby competitor configurations, normalize to 30-day effective prices, apply rule-based quality adjustment, and judge whether price movement is explainable.

Do not compare prices by package names alone. VIP/KVIP/SVIP/XVIP names are platform-specific and may represent different configuration tiers.

## When to use

Use this skill when the user asks for:

- 云手机基准价监测
- UgPhone 作为参照系的竞品比价
- VSPhone / Redfinger / LDCloud 价格变化
- 近似配置、质量调整价格、30 天等效价
- 活动价、降价、涨价、库存、地区、促销文案变化
- SEO / GEO / 运营竞品价格分析

## Safety and accuracy rules

1. Do not fabricate fields.
2. If a field is not visible in the page, DOM, or API response, leave it blank/null and add notes when a calculation cannot be made.
3. Never click buttons that may create a purchase, order, checkout, payment, subscription, renewal, or confirmation.
4. If the page is blocked by login, CAPTCHA, region restrictions, anti-bot checks, or JavaScript problems, save screenshot + HTML and record the issue in `run_summary.json`.
5. Prefer API responses over DOM extraction when structured product data is available.
6. Do not split output rows by server address. Write all supported servers into `supported_server_regions`.
7. Treat baseline files and `output/auth/` as private data.
8. Do not upload auth, cookies, tokens, account information, or private baseline workbooks.

## Baseline workflow

From the skill directory:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Create or overwrite the default baseline after a verified collection:

```bash
python run.py --init-baseline
```

Daily or recurring monitoring:

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

Use custom quality monitor settings:

```bash
python run.py --quality-price-config path/to/config.json
```

## Login workflow

If a site requires login, use a visible browser or the dedicated login helper. When using the helper, let the user finish login and continue only after the user says `已登录`.

Saved login states should stay under `output/auth/` and must not be uploaded to GitHub.

## Output

The tool creates an output directory like:

```text
output/cloud_phone_monitor_YYYYMMDD_HHMMSS/
```

Files:

- `products.csv`
- `products.xlsx`
- `products.jsonl`
- `product_brief.txt`
- `daily_changes.xlsx`
- `baseline_products_updated.xlsx`
- `quality_price_report.xlsx`
- `run_summary.json`
- `api_candidates.json`
- `page_artifacts/screenshots/`
- `page_artifacts/html/`
- `page_artifacts/api_responses/`

`quality_price_report.xlsx` contains:

- `配置配对建议`
- `质量调整价格明细`
- `UG相对竞品指数`
- `变价合理性判断`
- `说明`

`daily_changes.xlsx` keeps the existing baseline-change sheets and adds `UG相近配置价格对比`, which uses the quality-adjusted nearby-configuration logic.

## Local dashboard

The skill includes a local read-only Vite/React dashboard under `dashboard/`.

```bash
cd dashboard
npm install
npm run dev
```

The dashboard is a business-facing price monitor, not a collection control panel. It must only show pricing, pairing, duration-bucket comparison, trends, product text changes, and metric explanations. Collection diagnostics are exported to `admin_diagnostics.json` for internal review and must not be loaded by the public dashboard.

The web dashboard must remain read-only. It must not expose a `Run Monitor` button, initialize baseline from the browser, execute crawlers, touch login state, or trigger purchase/order/payment/subscription actions. If a user wants to run collection manually, use:

```bash
python run.py
```

Frontend routes:

- `#/price-overview`: business summary, core duration buckets, market-position distribution, and attention items.
- `#/pairing`: configuration pairing evidence, not price comparison.
- `#/duration-prices`: core page for 1/3/7/15/30/60/90/180/365-day same-duration price comparison.
- `#/trends`: current price, previous price, 7-day average, 30-day average, and line chart.
- `#/price-changes`: current-price movement tracking; no list price or discount-rate metrics.
- `#/product-text`: current and previous product/promotion text.
- `#/metrics`: plain-language metric definitions.

Pairing is evidence only. Final judgement should come from same-duration current prices, `competitor_median_price`, `ugphone_relative_index`, `market_position_label`, product text changes, `reason_code`, and `alert_level`.

Frontend JSON files:

- `frontend_price_overview.json`
- `pairing_matrix.json`
- `duration_price_comparison.json`
- `price_trends.json`
- `price_change_tracking.json`
- `product_text_changes.json`
- `metric_definitions.json`

Internal-only diagnostics:

- `admin_diagnostics.json`

Core frontend duration buckets are exactly 7, 30, 90, 180, and 365 days. Short/hour/non-core durations must be marked as `duration_bucket = other`, `is_core_duration_bucket = false`, and excluded from core price comparison.

## Daily scheduler

Daily data updates should be handled by an OS-level scheduler, not by the web UI.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_daily_monitor_windows.ps1
```

This creates a weekday 10:00 Task Scheduler task named `CloudPhoneMonitorDaily` and writes logs to:

```text
output/scheduler_logs/
```

macOS/Linux:

```bash
bash scripts/setup_daily_monitor_cron.sh
```

The script prints a crontab example for weekday 10:00. Review it before adding it with `crontab -e`.

Scheduler state is exported as `schedule_status.json` inside `dashboard_data`. If no scheduler is installed, the dashboard must show `scheduler_enabled: false` / `manual` instead of pretending automatic collection is active.

## Core metrics

- `current_price`: current transaction price.
- `previous_price`: previous successful same-product same-duration price.
- `baseline_price`: baseline same-product same-duration price.
- `price_change_pct`: current price change versus previous price.
- `seven_day_avg_price` / `thirty_day_avg_price`: historical transaction-price averages with sample counts.
- `config_similarity_score` / `comparability_level`: pairing quality.
- `competitor_median_price`: same-duration median of strong/adjusted competitor current prices.
- `ugphone_relative_index`: UgPhone current price divided by competitor median price, multiplied by 100.
- `promotion_text_changed`: whether product/promotion text changed.
- `reason_code`: current-price explanation tag, such as `price_up`, `price_down`, `promotion_text_changed`, `short_duration_excluded`, or `abnormal_price_change`.
- `alert_level`: `critical`, `warning`, `info`, or `none`.

## Configuration pairing rules

UgPhone is the base platform. Manual mappings are preferred but are not hard filters. If a recommended competitor tier is missing from the collection, the monitor falls back to automatic top-scoring nearby configurations.

Similarity score is based on:

- Android version
- CPU cores
- RAM GB
- Storage GB
- Supported server region overlap
- Duration comparability

Comparability levels:

- `strong_match`: score >= 90
- `adjusted_match`: 75 <= score < 90
- `weak_match`: 60 <= score < 75
- `not_comparable`: score < 60

Only `strong_match` and `adjusted_match` enter the core competitor median for `ugphone_relative_index`. `weak_match` is reported for context.

## Expected workflow for Codex

1. Confirm dependencies are installed.
2. Run headed/login flow if a site requires login.
3. Run collection.
4. Review `run_summary.json`, especially `quality_price_monitor`.
5. Review `products.xlsx` for product table quality.
6. Review `daily_changes.xlsx` for baseline changes and nearby UG comparisons.
7. Review `quality_price_report.xlsx` for pairing quality, adjusted price, relative index, and reason codes.
8. Use the local dashboard for read-only visual review when the user wants an interactive view.
9. If a platform returns no records, inspect screenshots, HTML, API responses, and blocked reasons.
10. Avoid changing scrapers unless collected fields are genuinely insufficient.

## GitHub upload guidance

Upload source code and docs only. Do not upload `output/`, `output/auth/`, `page_artifacts/`, `dashboard/node_modules/`, `dashboard/dist/`, or private baseline workbooks under `baselines/`.



## Redfinger price-SKU integrity rule

Redfinger price data is valid only when it comes from the signed `getGoods` purchase API or from a visible card that contains both a price and a duration. The scraper must select a plan, Android version, and server before treating a page state as collected. Public game recommendations, wallet balances, navigation labels, loading skeletons, and plan-tab text are diagnostic evidence only and must never enter `products.xlsx` as product records.

When no valid Redfinger price SKU is extracted, inspect `page_artifacts/redfinger_price_diagnostic.json` together with screenshots and API responses. Do not publish the resulting dashboard build.


## 2026-07-02 诊断与发布可靠性修复

- 页面截图与 HTML 证据文件改用受控短路径和哈希文件名；保存失败时返回空路径并进入 Redfinger 组合级摘要。
- Redfinger 每次采集输出 `page_artifacts/redfinger_collection_summary.json`，用于区分价格采集失败、组合覆盖不足和仅诊断附件失败。
- 看板平台状态拆分为 `collection_status` 与 `baseline_coverage_status`；旧的 `status` 保持与真实采集状态一致。
- 自动发布脚本不会再因上一轮的产品数量异常阻断下一轮采集，但仍会阻断登录、会话、验证码、反爬与 401/403 等认证/访问问题。
- 发布前自动将 Git `origin` 更新为 `Nikolaustis/Cloud-Phone-Price-Dashboard-Site`，并推送当前分支。
