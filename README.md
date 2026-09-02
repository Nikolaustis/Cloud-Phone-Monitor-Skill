# Cloud Phone Baseline Price Monitor

Cloud Phone Baseline Price Monitor 用于采集和比较 UgPhone、VSPhone、Redfinger、LDCloud 的云手机产品价格，并提供本地 Dashboard、历史趋势、同周期价格比较和配置相似度分析。

## 主要功能

- **多平台价格采集**：统一整理 UgPhone、VSPhone、Redfinger、LDCloud 的套餐、配置、地区、购买时长、价格和促销信息。
- **基准价监测**：将当前价格与已确认的 baseline 比较，识别涨价、降价、缺失和促销文案变化。
- **同周期价格比较**：按相同购买时长比较不同平台的成交价。
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

也可以单独安装依赖：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_dependencies_windows.ps1
```

更完整的安装说明见 [INSTALL_GUIDE.md](INSTALL_GUIDE.md)。

## 登录

部分平台需要登录后才能读取完整价格。

```bash
python run.py --headed
```

登录状态、Cookie、Token 和账号信息属于本地私有数据，不应上传或共享。

## 基本使用

采集：

```bash
python run.py
```

第一次确认采集结果无误后初始化 baseline：

```bash
python run.py --init-baseline
```

默认 baseline：

```text
baselines/products_baseline.xlsx
```

## Dashboard

本地查看：

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

Dashboard 是只读界面，不包含购买、支付、续费或下单能力。

## 可选：发布到 GitHub Pages

默认情况下，自动更新只执行：

```text
采集 → 历史重建 → Dashboard 构建 → 数据校验
```

不会执行 Git push。

如果希望把构建后的 Dashboard 发布到自己的 GitHub Pages 仓库：

1. 将 `publisher.local.example.json` 复制为 `publisher.local.json`。
2. 在 `publisher.local.json` 中填写自己的 `dashboard_site_remote`。
3. 可选填写本地仓库路径、分支和提交信息前缀。

`publisher.local.json` 已被 `.gitignore` 排除，仅作为本地配置使用。

## 缺失数据与历史连续性

采集不到某个普通商品并不等于商品已经下架。系统会区分当前真实采集值、暂时缺失采集、不可售、已下架、历史沿用值以及未知状态。

## 数据安全

以下内容应保留在本地：

```text
output/auth/
baselines/
output/.history_cache/
publisher.local.json
```

不要公开 Cookie、Token、Playwright storage state、持久化浏览器登录配置、账号信息、私有 baseline、本地发布配置或未脱敏诊断数据。

详见 [DEPLOYMENT_DATA_GUIDE.md](DEPLOYMENT_DATA_GUIDE.md)。

## Disclaimer

本项目用于价格监测、数据整理和业务分析。使用时应遵守相关网站的服务条款、账号规则和当地法律法规。
