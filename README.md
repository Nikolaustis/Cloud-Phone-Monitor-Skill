# Cloud Phone Baseline Price Monitor

> 将原本只存在于本机 `C:\Sites` 的 Dashboard 校验与 GitHub Pages 发布层正式纳入源码仓库。`deployment/windows/` 是发布脚本的唯一源码来源；`C:\Sites` 只是安装目标。

这个 Codex skill 用来采集 UgPhone、VSPhone、Redfinger、LDCloud 的云手机产品价格，并输出两类监测：

- 同商品基准价监测：用固定 baseline 跟踪每日价格、促销文案、缺失和涨跌。
- 以 UgPhone 为基准的近似配置质量调整比价：不要按套餐名直接比价，而是根据 Android、CPU、内存、存储、地区和购买时长计算相似度，再做质量调整后的 30 天等效价比较。

## Install

Windows 推荐直接使用安装器：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

它会把源码覆盖到默认 Skill 目录，并把与当前源码匹配的发布层安装到 `C:\Sites`；`output/`、`baselines/`、`dashboard/node_modules/` 和 `dashboard/dist/` 不会被删除。

首次部署依赖时可运行：

```powershell
.\INSTALL.ps1 -InstallDependencies
```

手工安装 Python/Playwright 依赖仍可使用：

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

### UgPhone / VSPhone 订阅与非订阅价格

UgPhone 与 VSPhone 都按 `purchase_mode` 区分两类价格：

- `subscription`：自动续费开启时的单品套餐卡价格。
- `non_subscription`：自动续费关闭时的单品套餐卡价格。

VSPhone 按“开启自动续费采集 → 关闭自动续费采集 → 恢复开启”的顺序运行，数量必须验证为 `1`，且只读取套餐卡本身的价格，不读取页面右下角的订单总计。VSPhone 非订阅价格仅采集 1、3、7、30、90、365 天。采集证据与失败原因写入 `page_artifacts/vsphone_collection_summary.json`。历史 VSPhone 数据没有 `purchase_mode` 时按 `subscription` 处理。

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

的 Windows 每日任务运行完整链路，而不是只执行 `python run.py`：

```text
登录态预检
→ 四平台采集
→ 增量历史重建
→ Vite build
→ 数据/压缩历史校验
→ dist 镜像到 Dashboard Site docs/
→ git commit / push
```

规范发布脚本位于源码：

```text
deployment/windows/update_cloud_phone_dashboard.ps1
```

安装后实际执行路径为：

```text
C:\Sites\update_cloud_phone_dashboard.ps1
```

创建/更新工作日 10:00 的任务：

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts/setup_daily_monitor_windows.ps1
```

如果本轮采集、历史重建和 build 已经成功，只需要重新上传，不要重新采集：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Sites\resume_dashboard_publish.ps1
```

日志写入 `logs/`，调度状态写入 `output/scheduler_logs/schedule_status.json`。macOS/Linux 的 `scripts/setup_daily_monitor_cron.sh` 仅提供 collection/rebuild 示例，不包含 Windows GitHub Pages 发布层。

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

压缩包本身就是干净的源码树，应该上传：

- `cloud_phone_monitor/`
- `dashboard/`（不含 `node_modules`、`dist`、生成的 `dashboard_data`）
- `deployment/windows/`
- `scripts/`
- `tools/`
- `tests/`
- `run.py`
- `rebuild_dashboard_history.py`
- `deployment_contract.json`
- `INSTALL.ps1`
- `PUBLISH_SOURCE_TO_GITHUB.ps1`
- `README.md` / `SKILL.md` / 部署说明文档
- `.gitignore` / `.gitattributes`

安装完成后可直接运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PUBLISH_SOURCE_TO_GITHUB.ps1
```

它会同步到 `Nikolaustis/Cloud-Phone-Monitor-Skill`，并删除旧仓库中误提交的 `__pycache__/`、`*.pyc` 以及其他运行/私有数据。

永远不要上传：`output/`、`output/auth/`、`baselines/`、`logs/`、`dashboard/node_modules/`、`dashboard/dist/`、登录态、Cookie、Token、账号信息和私有 baseline。

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


## Deployment Integration

- `deployment_contract.json` 固定数据 schema、历史存储格式和发布能力，用于确保 Skill 与 `C:\Sites` 发布层兼容。
- `price_trends.json.gz` 与 `price_trends_chunks/*.json.gz` 是历史静态资源格式。
- `deployment/windows/` 是 `C:\Sites` 发布代码的唯一源码来源；升级时直接覆盖 canonical publisher，不再对旧脚本做脆弱的文本 patch。
- 发布校验允许业务层 partial coverage（由 carry-forward 处理），但会阻断认证/反爬失败、平台 0 records、缺失/损坏的 Dashboard 必需文件以及 gzip 历史损坏。
