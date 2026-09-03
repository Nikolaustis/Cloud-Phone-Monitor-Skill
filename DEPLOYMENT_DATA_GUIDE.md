# Data and Privacy Guide

本文档说明 Cloud Phone Baseline Price Monitor 的本地数据、缓存、登录状态、发布配置和备份边界。

## 本地运行数据

采集结果默认保存在：

```text
output/
```

这些文件通常不属于源码的一部分。

## 登录状态

登录相关数据通常位于：

```text
output/auth/
```

其中可能包含 Playwright storage state、Cookie、本地浏览器登录状态和持久化浏览器 profile。这些内容属于敏感数据，不应上传到公共仓库。

用于自动采集的认证必须由**本机 Playwright Chromium** 建立。ChatGPT Work / Cloud Browser 的 Cookie、localStorage、sessionStorage 与本机项目隔离，不能作为本地采集器认证材料的来源。

当 Work / Codex 的本地 Agent 使用两阶段登录协议时，还会暂时创建：

```text
output/auth/<platform>_login_agent_session.json
output/auth/<platform>_login_stdout.log
output/auth/<platform>_login_stderr.log
```

其中 `*_login_agent_session.json` 只保存本地进程 id、Skill 路径和阶段状态等编排信息；登录完成或取消后应自动删除。stdout/stderr 日志用于本地故障诊断。它们虽然不应主动保存密码，但仍可能包含运行环境、路径或站点错误信息，因此同样按私有本地数据处理，不应上传公共仓库。

UgPhone 的长期/兼容/短期认证材料分别为：

```text
output/auth/ugphone_profile/
output/auth/ugphone_state.json
output/auth/ugphone_runtime_context.json
```

`ugphone_runtime_context.json` 是短期运行桥接，不替代 persistent profile 的长期认证地位。

## Baseline

默认 baseline：

```text
baselines/products_baseline.xlsx
```

建议作为本地或私有业务数据保存。

## 历史缓存

增量历史重建可能使用：

```text
output/.history_cache/
```

## 本地发布配置

可选 GitHub Pages 发布使用：

```text
publisher.local.json
```

公共仓库只提供：

```text
publisher.local.example.json
```

`publisher.local.json` 已被 `.gitignore` 排除。未配置时，系统仅在本地完成采集、历史重建、Dashboard 构建和验证，不执行远程 Git 发布。

## Dashboard 生成文件

常见生成目录：

```text
dashboard/dist/
dashboard/public/dashboard_data/
```

这些是生成文件，不是核心源码。

## 不建议公开的内容

- Cookie
- Token
- 账号信息
- storage state
- 浏览器 profile
- `output/auth/*_login_agent_session.json`
- `output/auth/*_login_stdout.log`
- `output/auth/*_login_stderr.log`
- 私有 baseline
- `publisher.local.json`
- 含敏感参数的 API 请求或响应
- 未脱敏的诊断附件
