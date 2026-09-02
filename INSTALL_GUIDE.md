# Installation Guide

本文档说明如何安装并开始使用 Cloud Phone Baseline Price Monitor。

## 1. 环境要求

建议环境：

- Windows 10 / 11
- Python 3.12+
- Node.js 与 npm
- Git（可选）
- Chromium / Playwright

## 2. 安装

下载或克隆仓库后，在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

如果是首次部署，并希望一并安装 Python、Playwright 和 Dashboard 依赖：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

也可以手工安装：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

然后安装 Dashboard 依赖：

```bash
cd dashboard
npm ci
```

## 3. 首次登录

部分平台需要登录后才能获取完整价格。

使用可见浏览器启动采集：

```bash
python run.py --headed
```

登录成功后，可将登录状态保留在本机的 `output/auth/` 中。

不要上传或共享：

- Cookie
- Token
- storage state
- 持久化浏览器配置
- 账号信息

## 4. 第一次采集

```bash
python run.py
```

完成后检查：

```text
output/cloud_phone_monitor_YYYYMMDD_HHMMSS/
```

重点确认：

- 各平台是否有有效产品记录
- 价格与购买周期是否合理
- Android / CPU / RAM / Storage 是否正确
- 地区是否完整
- `run_summary.json` 是否存在异常

## 5. 初始化 baseline

确认首次采集结果无误后：

```bash
python run.py --init-baseline
```

默认 baseline 保存到：

```text
baselines/products_baseline.xlsx
```

以后日常运行：

```bash
python run.py
```

## 6. Dashboard

开发模式：

```bash
cd dashboard
npm run dev
```

生成历史数据：

```bash
python rebuild_dashboard_history.py --incremental
```

构建静态页面：

```bash
cd dashboard
npm run build
```

## 7. 更新历史数据

日常采集完成后，可执行：

```bash
python rebuild_dashboard_history.py --incremental
```

只有在需要完整重建历史数据时才使用：

```bash
python rebuild_dashboard_history.py --full
```

## 8. 常见问题

### 某个平台没有数据

先检查：

- 登录是否失效
- 是否出现验证码或访问限制
- 页面结构是否发生变化
- `run_summary.json`
- `page_artifacts/` 中的截图、HTML 和 API 诊断

### 某个套餐当天没有采集到

短期缺失不一定表示商品下架。系统会区分临时采集缺失、不可售和已下架状态，并在适用时沿用最近一次真实观测值。

### Dashboard 没有更新

重新执行：

```bash
python rebuild_dashboard_history.py --incremental
cd dashboard
npm run build
```

## 9. 数据备份

如果需要保留长期历史，建议备份：

```text
output/
baselines/
```

登录状态属于敏感数据，应单独、安全地保存，不建议通过公共代码仓库同步。
