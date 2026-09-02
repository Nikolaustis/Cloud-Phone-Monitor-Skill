# Data and Privacy Guide

本文档说明 Cloud Phone Baseline Price Monitor 的本地数据、缓存、登录状态和备份边界。

## 本地运行数据

采集结果默认保存在：

```text
output/
```

其中可能包含：

- 产品表
- 历史价格
- 运行摘要
- API 诊断
- 页面截图
- HTML 证据
- Dashboard 数据

这些文件通常不属于源码的一部分。

## 登录状态

登录相关数据通常位于：

```text
output/auth/
```

其中可能包含：

- Playwright storage state
- Cookie
- 本地浏览器登录状态
- UgPhone 持久化浏览器 profile

这些内容属于敏感数据。

请勿：

- 上传到公共 GitHub 仓库
- 通过聊天、工单或公开链接分享
- 与不受信任的第三方同步

如果怀疑登录状态已经泄露，应重新登录并使旧会话失效。

## Baseline

默认 baseline：

```text
baselines/products_baseline.xlsx
```

Baseline 用于比较同商品历史价格，因此可能反映内部业务使用的参考数据。

如需跨设备迁移，可单独备份，但不建议公开。

## 历史缓存

增量历史重建可能使用：

```text
output/.history_cache/
```

该目录用于提高历史重建效率。删除缓存不会删除原始历史数据，但下一次重建可能耗时更长。

## Dashboard 生成文件

常见生成目录：

```text
dashboard/dist/
dashboard/public/dashboard_data/
```

这些是根据本地采集结果生成的静态资源，不是核心源码。

如果 Dashboard 显示异常，可以重新执行：

```bash
python rebuild_dashboard_history.py --incremental
cd dashboard
npm run build
```

## 建议备份

如果希望在重装系统或迁移电脑后保持价格历史连续，建议备份：

```text
output/
baselines/
```

如确实需要保留登录状态，应使用受保护的本地或加密备份，并与普通项目文件分开。

## 恢复

迁移到新环境时，一般流程为：

1. 安装项目和依赖。
2. 恢复 `output/` 与 `baselines/`。
3. 在本机重新完成各平台登录。
4. 执行：

```bash
python rebuild_dashboard_history.py --incremental
```

5. 重新构建 Dashboard：

```bash
cd dashboard
npm run build
```

## 不建议公开的内容

无论是否包含在其他输出中，下列内容都应视为私有：

- Cookie
- Token
- 账号信息
- storage state
- 浏览器 profile
- 私有 baseline
- 含敏感参数的 API 请求或响应
- 未脱敏的诊断附件
