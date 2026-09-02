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

```bash
python run.py --headed
```

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
