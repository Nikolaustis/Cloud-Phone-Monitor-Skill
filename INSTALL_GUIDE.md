# Installation Guide

本文档说明如何安装并开始使用 Cloud Phone Baseline Price Monitor。

## 1. 环境要求

建议环境：

- Windows 10 / 11
- Python 3.12+
- Node.js 与 npm
- Chromium / Playwright
- Git（仅在使用可选 GitHub Pages 发布时需要）

## 2. 安装

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

首次部署并安装依赖：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

也可以单独安装依赖：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_dependencies_windows.ps1
```

## 3. 首次登录

安装后的正式登录入口是 `LOGIN.ps1`：

```powershell
.\LOGIN.ps1 UgPhone
.\LOGIN.ps1 VSPhone
.\LOGIN.ps1 Redfinger
.\LOGIN.ps1 LDCloud
```

脚本会启动**本机 Playwright Chromium**。必须在这个弹出的浏览器窗口中完成登录；登录完成后保持窗口打开，再回到 PowerShell 按 Enter，由脚本自动验证并保存状态。

不要使用 ChatGPT Work / Cloud Browser 完成用于自动采集的登录。Cloud Browser 的 Cookie、localStorage、sessionStorage 等会话数据与本机项目隔离，不能写入或替代 `output/auth/` 中的本地认证材料。

UgPhone 登录成功后应建立：

```text
output/auth/ugphone_state.json
output/auth/ugphone_profile/
output/auth/ugphone_runtime_context.json
```

UgPhone 会在保存后重新打开 persistent profile，并用与计划任务等价的 headless 环境再次验证。其他平台当前保存 Playwright storage state；其平台特定 live-auth 验证严格程度低于 UgPhone。

`python run.py --headed` 仅作为可见模式调试采集入口，不作为正式的首次登录/持久化入口。

登录状态应保留在本机，不要上传或共享 Cookie、Token、storage state、持久化浏览器配置或账号信息。

## 4. 第一次采集

```bash
python run.py
```

确认输出无误后：

```bash
python run.py --init-baseline
```

## 5. Dashboard

本地查看：

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

## 6. 可选 GitHub Pages 发布

GitHub Pages 发布默认关闭。

如需启用：

```powershell
Copy-Item .\publisher.local.example.json .\publisher.local.json
```

编辑 `publisher.local.json`，填写自己的 `dashboard_site_remote`。

没有该本地配置时，Windows 日常任务只执行采集、历史重建、构建和验证，不会执行 `git clone`、`git commit` 或 `git push`。

## 7. 数据备份

长期历史建议备份：

```text
output/
baselines/
```

登录状态和 `publisher.local.json` 属于本地配置，应单独、安全保存。
