# Cloud Phone Baseline Price Monitor

这个 Codex skill 用来采集 UgPhone、VSPhone、Redfinger、LDCloud 的云手机产品价格，并输出两类监测：

- 同商品基准价监测：用固定 baseline 跟踪每日价格、促销文案、缺失和涨跌。
- 以 UgPhone 为基准的近似配置质量调整比价：不要按套餐名直接比价，而是根据 Android、CPU、内存、存储、地区和购买时长计算相似度，再做质量调整后的 30 天等效价比较。

## Install

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Baseline Workflow

第一次确认产品表质量后，把当前输出保存为基准：

```bash
python run.py --init-baseline
```

默认基准文件路径：

```text
baselines/products_baseline.xlsx
```

后续日常监测直接运行：

```bash
python run.py
```

如果只想采集产品表，不做同商品 baseline 对比：

```bash
python run.py --skip-baseline-monitor
```

如果只想跳过 UgPhone 质量调整比价：

```bash
python run.py --skip-quality-price-monitor
```

可选质量比价配置：

```bash
python run.py --quality-price-config path/to/config.json
```

## Login

需要人工登录或调试页面时使用可见浏览器：

```bash
python run.py --headed
```

也可以使用已保存的 Playwright 登录态：

```bash
python run.py --platform Redfinger --storage-state output/auth/redfinger_state.json
```

登录态必须留在 `output/auth/`，不要上传。

## Output

每次运行会创建：

```text
output/cloud_phone_monitor_YYYYMMDD_HHMMSS/
  products.csv
  products.xlsx
  products.jsonl
  product_brief.txt
  daily_changes.xlsx
  baseline_products_updated.xlsx
  quality_price_report.xlsx
  run_summary.json
  api_candidates.json
  page_artifacts/
    screenshots/
    html/
    api_responses/
```

`products.xlsx` 按平台分 sheet：UgPhone、VSPhone、Redfinger、LDCloud。

`daily_changes.xlsx` 保留原有 baseline 变化，并新增 `UG相近配置价格对比`，该 sheet 使用相似度和质量调整逻辑，不再只按 CPU/内存/存储/时长完全一致匹配。

`quality_price_report.xlsx` 包含：

- `配置配对建议`：UgPhone 配置与竞品候选配置的相似度、配对来源和备注。
- `质量调整价格明细`：30 天等效价、折扣率、质量调整系数、调整后价差。
- `UG相对竞品指数`：UgPhone 相对核心竞品质量调整价中位数的指数。
- `变价合理性判断`：当前与 baseline 的 30 天等效价、原价、折扣率、促销、地区、库存变化判断。
- `说明`：核心指标和标签解释。

## Local Dashboard

本项目包含一个本地可查看的只读 Dashboard，目录在 `dashboard/`。它只读取 `dashboard/public/dashboard_data/*.json` 或 `output/latest/dashboard_data/*.json` 中的非敏感摘要数据，不读取 `output/auth/`，也不会暴露 cookie、token 或 Playwright storage state。

Dashboard 本身不抓取数据，不提供 `Run Monitor`，也不会触发购买、下单、支付或订阅。每日数据更新应由系统级任务完成；手动采集请在命令行运行 `python run.py`。

启动方式：

```bash
cd dashboard
npm install
npm run dev
```

默认会在本地 Vite 地址打开，例如：

```text
http://127.0.0.1:5173/
```

当前 Dashboard 优先读取 `dashboard/public/dashboard_data/*.json` 中的前台业务 JSON，并在缺少静态数据时回退到本地 mock 数据。界面支持简体中文和 English 切换。

页面结构：

- `#/price-overview`：价格概览，只展示更新时间、基准配置数、核心天数、价格位置分布和关注项。
- `#/pairing`：配置配对，说明 UgPhone 与 VSPhone / Redfinger / LDCloud 如何配对。
- `#/duration-prices`：分天数价格对比，按 1/3/7/15/30/60/90/180/365 天分 tab 比较成交价。
- `#/trends`：价格趋势，展示当前价、上次价、7日均价、30日均价和折线图。
- `#/price-changes`：价格变化追踪，只追踪成交价变化，不使用原价或折扣率。
- `#/product-text`：商品文本，展示当前/上次商品或活动文案。
- `#/metrics`：指标说明，用通俗中文解释所有核心指标。

后台诊断数据单独写入 `dashboard_data/admin_diagnostics.json`，前台页面不加载它。采集状态、登录状态、fallback、失败原因和内部路径只用于内部排查，不出现在业务看板。

配对不是最终结论：不同平台套餐名含义不同，配对只用于证明某个竞品能否进入同天数核心竞品中位数。最终判断来自 `duration_price_comparison.json` 中的同购买天数成交价、`competitor_median_price`、`ugphone_relative_index`、`market_position_label` 和商品文本变化。

## Daily Auto Update

Dashboard 数据由每日自动任务更新，网页只重新加载已经生成的 `dashboard_data`。

Windows Task Scheduler：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_daily_monitor_windows.ps1
```

默认创建任务：

```text
CloudPhoneMonitorDaily
```

默认每个工作日 10:00 在当前 skill 根目录运行：

```bash
python run.py
```

日志写入：

```text
output/scheduler_logs/
```

macOS/Linux cron 示例：

```bash
bash scripts/setup_daily_monitor_cron.sh
```

脚本会输出 crontab 示例；请审阅后手动加入 `crontab -e`。

手动运行一次采集：

```bash
python run.py
```

调度状态会导出到后台/状态 JSON：

```text
output/latest/dashboard_data/schedule_status.json
dashboard/public/dashboard_data/schedule_status.json
```

如果超过 30 小时未更新，Dashboard 显示 warning；超过 48 小时显示 critical/outdated。

## Core Metrics

- `current_price`：当前成交价。
- `previous_price`：上一次成功采集的同商品同天数成交价。
- `baseline_price`：baseline 对应商品和购买天数的成交价。
- `price_change_pct`：当前价相对上次价的变化比例。
- `seven_day_avg_price` / `thirty_day_avg_price`：历史样本均价；样本不足时只作辅助参考。
- `config_similarity_score` / `comparability_level`：配置相似度和配对等级。
- `competitor_median_price`：同购买天数下 strong/adjusted 竞品当前价中位数。
- `ugphone_relative_index`：UgPhone 当前价 / 竞品中位价 * 100。
- `promotion_text_changed`：商品/活动文本是否变化。
- `reason_code`：基于现价和文本变化判断，如 `price_up`、`price_down`、`promotion_text_changed`、`short_duration_excluded`。
- `alert_level`：`critical`、`warning`、`info`、`none`。

前台核心价格比较只使用这些购买天数：

```text
1 / 3 / 7 / 15 / 30 / 60 / 90 / 180 / 365
```

4 小时、45 天、120 天、活动组合包、多设备包等非核心周期会标记为 `duration_bucket = other`；1/3/15/60 天会作为独立核心购买天数展示。

## Why Not Compare Package Names Directly

不同平台的 VIP、KVIP、SVIP、XVIP 含义不同，同名套餐可能配置不同，不同名套餐也可能配置接近。套餐名只作为手工推荐配对的线索，核心比较使用配置相似度和质量调整价。

## Important Fields

| Field | Meaning |
|---|---|
| platform | UgPhone / VSPhone / Redfinger / LDCloud |
| supported_server_regions | 该商品支持的全部服务器地区 |
| product_model | 套餐或 SKU，例如 UVIP / KVIP / SVIP / XVIP |
| device_model | 设备机型或平台内部型号 |
| android_version | 安卓版本；无法确认时留空 |
| cpu | CPU 核心数 |
| ram | 内存 |
| storage | 存储 |
| price | 当前实付价 |
| original_price | 页面/API 暴露的原价 |
| duration | 购买时长 |
| promotion_text | 活动文案 |
| stock_status | 库存状态 |

## Upload To GitHub

建议上传源码和文档：

- `SKILL.md`
- `README.md`
- `requirements.txt`
- `config.example.json`
- `install_windows.ps1`
- `run.py`
- `run_windows.bat`
- `scripts/`
- `cloud_phone_monitor/`
- `dashboard/`
- `.gitignore`

不要上传：

- `output/`
- `output/auth/`
- `baselines/*.xlsx`
- `page_artifacts/`
- `__pycache__/`
- `*.pyc`
- `dashboard/node_modules/`
- `dashboard/dist/`
- 任何登录态、Cookie、Token、账号信息或私有价格基准文件



## Redfinger price-SKU integrity

Redfinger 的价格 SKU 必须来自已登录购买页的 `getGoods` 接口，或来自同时含有**价格**与**时长**的可见套餐卡片。采集流程会依次选择套餐、Android 版本和服务器；游戏推荐、钱包余额、导航文字、加载骨架和套餐标签仅保留为诊断证据，不会再写入 `products.xlsx`。

如 Redfinger 未采集到有效价格 SKU，请查看本次输出中的：

```text
page_artifacts/redfinger_price_diagnostic.json
page_artifacts/screenshots/
page_artifacts/api_responses/
```

这种情况不应手工发布看板构建产物。


## 2026-07-02 诊断与发布可靠性修复

- 页面截图与 HTML 证据文件改用受控短路径和哈希文件名；保存失败时返回空路径并进入 Redfinger 组合级摘要。
- Redfinger 每次采集输出 `page_artifacts/redfinger_collection_summary.json`，用于区分价格采集失败、组合覆盖不足和仅诊断附件失败。
- 看板平台状态拆分为 `collection_status` 与 `baseline_coverage_status`；旧的 `status` 保持与真实采集状态一致。
- 自动发布脚本不会再因上一轮的产品数量异常阻断下一轮采集，但仍会阻断登录、会话、验证码、反爬与 401/403 等认证/访问问题。
- 发布前自动将 Git `origin` 更新为 `Nikolaustis/Cloud-Phone-Price-Dashboard-Site`，并推送当前分支。
