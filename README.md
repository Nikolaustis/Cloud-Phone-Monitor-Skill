# Cloud Phone Baseline Price Monitor

Cloud Phone Baseline Price Monitor 用于采集和比较 UgPhone、VSPhone、Redfinger、LDCloud 的云手机产品价格，并提供本地 Dashboard、历史趋势、同周期价格比较和配置相似度分析。

## 主要功能

- **多平台价格采集**：统一整理 UgPhone、VSPhone、Redfinger、LDCloud 的套餐、配置、地区、购买时长、价格和促销信息。
- **基准价监测**：将当前价格与已确认的 baseline 比较，识别涨价、降价、缺失和促销文案变化。
- **同周期价格比较**：按相同购买时长比较不同平台的成交价，避免只按 VIP/KVIP/SVIP 等套餐名称直接横向比较。
- **近似配置配对**：根据 Android、CPU、内存、存储、地区和购买时长评估配置相似度。
- **订阅 / 非订阅价格**：UgPhone 与 VSPhone 通过 `purchase_mode` 区分自动续费开启和关闭时的价格。
- **历史趋势**：支持当前价、上次价格、7 日均价、30 日均价和长期价格趋势。
- **只读 Dashboard**：网页只展示采集后的业务数据，不会从浏览器触发购买、支付、订阅或采集操作。

## 支持的平台

| Platform | 主要采集内容 |
|---|---|
| UgPhone | 套餐、Android 版本、地区、购买周期、订阅/非订阅价格 |
| VSPhone | 套餐、配置、购买周期、订阅/非订阅价格 |
| Redfinger | 套餐、Android、地区、有效价格 SKU |
| LDCloud | 套餐、配置、地区、购买周期和价格 |

## 安装

### Windows

下载或克隆仓库后，在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

首次使用并需要安装依赖时：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

也可以手工安装 Python 和 Playwright 依赖：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Dashboard 依赖：

```bash
cd dashboard
npm ci
```

更完整的安装说明见 [INSTALL_GUIDE.md](INSTALL_GUIDE.md)。

## 登录

部分平台需要登录后才能读取完整价格。

需要人工登录时可使用可见浏览器：

```bash
python run.py --headed
```

已保存的 Playwright 登录状态可以通过参数使用，例如：

```bash
python run.py --platform Redfinger --storage-state output/auth/redfinger_state.json
```

登录状态、Cookie、Token 和账号信息属于本地私有数据，不应上传或共享。

## 基本使用

### 1. 采集

```bash
python run.py
```

### 2. 初始化 baseline

第一次确认采集结果无误后：

```bash
python run.py --init-baseline
```

默认 baseline：

```text
baselines/products_baseline.xlsx
```

### 3. 可选运行模式

只采集产品表，不进行同商品 baseline 比较：

```bash
python run.py --skip-baseline-monitor
```

跳过 UgPhone 近似配置质量调整比价：

```bash
python run.py --skip-quality-price-monitor
```

使用自定义质量比价配置：

```bash
python run.py --quality-price-config path/to/config.json
```

## 输出

每次采集会创建类似目录：

```text
output/cloud_phone_monitor_YYYYMMDD_HHMMSS/
```

主要文件包括：

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

`quality_price_report.xlsx` 主要包括：

- 配置配对建议
- 质量调整价格明细
- UG 相对竞品指数
- 变价合理性判断
- 指标说明

## Dashboard

Dashboard 位于：

```text
dashboard/
```

本地开发查看：

```bash
cd dashboard
npm ci
npm run dev
```

默认地址通常为：

```text
http://127.0.0.1:5173/
```

生成历史数据并构建静态 Dashboard：

```bash
python rebuild_dashboard_history.py --incremental
cd dashboard
npm run build
```

主要页面：

- `#/price-overview`：价格概览
- `#/pairing`：配置配对
- `#/duration-prices`：同购买周期价格比较
- `#/trends`：价格趋势
- `#/price-changes`：价格变化
- `#/product-text`：商品/促销文本
- `#/metrics`：指标说明

Dashboard 是只读界面，不包含购买、支付、续费或下单能力。

## 价格比较原则

不同平台的 VIP、KVIP、SVIP、XVIP 等名称不能直接视为同等级配置。

核心比较优先使用：

- Android 版本
- CPU 核心数
- RAM
- 存储
- 支持地区
- 购买时长
- 当前成交价

配置相似度分为：

- `strong_match`：相似度 ≥ 90
- `adjusted_match`：75–89
- `weak_match`：60–74
- `not_comparable`：低于 60

`strong_match` 和 `adjusted_match` 可进入核心竞品价格中位数；`weak_match` 只作为参考。

## 核心购买周期

Dashboard 的主要比较周期为：

```text
1 / 3 / 7 / 15 / 30 / 60 / 90 / 180 / 365 天
```

其他周期会保留为非核心数据，但不会混入核心同周期比较。

## 缺失数据与历史连续性

采集不到某个普通商品并不等于商品已经下架。

系统会区分：

- 当前真实采集值
- 暂时缺失采集
- 不可售
- 已下架
- 历史沿用值
- 不适用或未知状态

只有在有充分证据时才会把商品视为不可售或下架；普通短期采集缺失可沿用最近一次真实观测值，以保持历史趋势连续。

## 数据安全

以下内容应始终保留在本地：

```text
output/auth/
baselines/
output/.history_cache/
```

不要公开：

- Cookie
- Token
- Playwright storage state
- 持久化浏览器登录配置
- 账号信息
- 私有 baseline
- 未脱敏的原始诊断数据

详细说明见 [DEPLOYMENT_DATA_GUIDE.md](DEPLOYMENT_DATA_GUIDE.md)。

## 数据质量与验证

系统会对登录状态、平台采集结果、核心 Dashboard 数据和历史压缩文件进行校验。部分套餐临时缺失通常会被标记为覆盖不足，而认证失败、平台完全无记录、关键数据文件损坏等情况会被视为严重异常。

详见 [VALIDATION.md](VALIDATION.md)。

## Redfinger 价格完整性

Redfinger 的有效价格必须来自：

- 已登录购买页的有效价格接口；或
- 同时包含**价格**和**购买时长**的可见套餐卡片。

游戏推荐、钱包余额、导航文字、加载骨架和单独的套餐标签不会被当作价格 SKU 写入产品表。

如果 Redfinger 没有采集到有效价格，可查看本次输出中的诊断信息：

```text
page_artifacts/redfinger_price_diagnostic.json
page_artifacts/screenshots/
page_artifacts/api_responses/
```

## License / Disclaimer

本项目用于价格监测、数据整理和业务分析。使用时应遵守相关网站的服务条款、账号规则和当地法律法规。
