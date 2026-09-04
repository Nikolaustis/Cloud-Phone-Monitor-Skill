# Cloud Phone Baseline Price Monitor

面向 **UgPhone、VSPhone、Redfinger、LDCloud** 的云手机价格监测与竞品分析 Skill。项目将 Playwright 采集、登录态持久化、基准价监测、同周期竞品比较和只读 Dashboard 组合为一套可重复部署的本地工作流。

> 本仓库只包含源码与公开配置模板。登录态、Cookie、Token、浏览器 profile、私有 baseline、运行日志和发布凭据均不属于公开源码。

## 核心能力

- **多平台价格采集**：统一整理套餐、配置、Android 版本、地区、购买周期、价格、库存和促销信息。
- **基准价监测**：比较当前观测值、上次有效观测与 baseline，识别涨跌、缺失和促销文案变化。
- **同周期竞品比较**：按购买时长和近似配置比较 UgPhone 与竞品价格。
- **订阅 / 非订阅区分**：UgPhone、VSPhone 显式区分自动续费开启与关闭的价格状态。
- **本地登录态持久化**：使用本机 Playwright Chromium 建立 collector authentication；不依赖系统 Chrome。
- **会话安全**：两阶段登录使用 UUID session、pending 状态、重新打开验证和事务式文件提交。
- **Persistent profile 互斥**：UgPhone 登录、登录预检和 canonical collector 共用 profile lock，避免并发打开同一 Chromium profile。
- **只读 Dashboard**：展示价格、趋势、配置配对、变价和文本变化，不从前端触发采集或购买行为。
- **公开发布防泄漏**：GitHub release 使用显式 allowlist staging，而不是直接打包开发工作区。

## 架构概览

```text
LOGIN.ps1 / run.py
        ↓
专用 .venv + session/profile guards
        ↓
Playwright Chromium
        ↓
平台 scraper / auth verifier
        ↓
output/（本地私有运行数据）
        ↓
历史重建 / Dashboard 导出
```

进一步说明：

- [架构说明](docs/ARCHITECTURE.md)
- [认证与登录态设计](docs/AUTHENTICATION_DESIGN.md)
- [公开发布流程](docs/RELEASE_PROCESS.md)
- [安全策略](SECURITY.md)
- [贡献说明](CONTRIBUTING.md)

## 支持平台

| Platform | 主要采集内容 | 登录态主要形式 |
|---|---|---|
| UgPhone | 套餐、Android、地区、购买周期、订阅/非订阅价格 | persistent profile + storage state + runtime context |
| VSPhone | 套餐、配置、购买周期、订阅/非订阅价格 | Playwright storage state |
| Redfinger | 套餐、Android、地区、有效价格 SKU | Playwright storage state |
| LDCloud | 套餐、配置、地区、购买周期、价格 | Playwright storage state |

## Windows 快速开始

### 1. 安装 Skill

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

新机器同时建立专用 Python / Playwright 运行环境：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\INSTALL.ps1 -InstallDependencies
```

也可以只安装 Python/Playwright 依赖：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\install_dependencies_windows.ps1
```

正式运行时固定为：

```text
<SkillRoot>\.venv\Scripts\python.exe
```

系统 Google Chrome 不是必需项；安装脚本会安装与 Python Playwright 配套的 Chromium，并执行一次 headless launch probe。

### 2. 建立本地登录态

人工 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone
```

Agent 两阶段登录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone -Start
```

在脚本打开的**本机 Chromium** 中完成登录后：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone -Complete
```

只有当前 session 完成验证后才会输出：

```text
LOGIN_AGENT_STATE=SAVED_AND_VERIFIED
```

ChatGPT Work / Cloud Browser 的远程浏览器会话不能作为本地 collector 登录态来源。

### 3. 采集

使用 canonical 入口：

```powershell
.\.venv\Scripts\python.exe .\run.py
```

单平台：

```powershell
.\.venv\Scripts\python.exe .\run.py --platform UgPhone
```

首次确认数据正确后初始化 baseline：

```powershell
.\.venv\Scripts\python.exe .\run.py --init-baseline
```

## Dashboard

本地开发：

```bash
cd dashboard
npm ci
npm run dev
```

历史重建：

```powershell
.\.venv\Scripts\python.exe .\rebuild_dashboard_history.py --incremental
```

Dashboard 是只读业务界面，不包含下单、购买、支付、续费或创建云手机实例的操作。

## 认证安全模型

登录成功不等价于“网页能打开”或“存在 Cookie”。验证要求至少包括认证证据和业务页面证据。

UgPhone 以 persistent profile 为长期主要认证权威，同时保存：

```text
output/auth/ugphone_profile/
output/auth/ugphone_state.json
output/auth/ugphone_runtime_context.json
```

新的 storage/runtime 文件先写入 session-specific pending 路径，验证成功后才提交。Persistent Chromium profile 本身不能参与普通多文件事务，因此通过重新打开验证和跨流程互斥降低并发风险。

## 测试

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\install_dependencies_windows.ps1 -InstallDevDependencies

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\RUN_TESTS.ps1
```

GitHub Actions 同时覆盖：

- Linux：Python 行为测试、公开文件策略、staging、Manifest 一致性。
- Windows：专用 `.venv`、Playwright Chromium launch probe、Windows PowerShell 状态机 smoke test。

## 公开发布

不要直接把整个开发工作目录上传到 GitHub。Canonical release：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\PREPARE_RELEASE.ps1
```

流程：

```text
测试
→ explicit allowlist staging
→ deployment_contract 公共字段净化
→ staged-source 校验
→ deterministic Manifest
→ Manifest 二次校验
→ deterministic public ZIP
```

`tools/public_release_policy.py` 是公开文件范围的单一权威来源。公开 staging 不包含 `.venv/`、`output/`、baselines、日志、profile、登录态、私有部署脚本或本地发布配置。Release 工具统一禁止写入 Python bytecode，ZIP 构建器也只接受 allowlist 文件和已验证 Manifest；任何 `__pycache__`、`.pyc` 或其他 staging 污染都会 fail-closed。

## 数据与隐私

以下内容必须保留在本地：

```text
output/
baselines/
.venv/
publisher.local.json
```

尤其不要公开：Cookie、Token、Playwright storage state、Chromium profile、runtime context、账号信息、未脱敏诊断数据和具体私有 Git remote。

详见 [DEPLOYMENT_DATA_GUIDE.md](DEPLOYMENT_DATA_GUIDE.md)。

## Disclaimer

本项目用于价格监测、数据整理和业务分析。使用者应自行确保采集和账号操作符合目标平台服务条款、账号规则及适用法律法规。
