# Data Quality and Validation

Cloud Phone Baseline Price Monitor 在采集、历史重建和 Dashboard 生成过程中会进行多层数据质量检查。

## 登录与访问检查

采集前应确认平台处于可访问状态。

用于自动采集的登录必须来自 `LOGIN.ps1` 启动的本机 Playwright Chromium。ChatGPT Work / Cloud Browser 的会话不能作为本机采集器的认证来源。

登录预检失败时，应在 Skill 根目录重新运行对应平台的本地登录入口：

```powershell
.\LOGIN.ps1 UgPhone
.\LOGIN.ps1 VSPhone
.\LOGIN.ps1 Redfinger
.\LOGIN.ps1 LDCloud
```

UgPhone 的正常本地认证基线包括 `ugphone_state.json`、`ugphone_profile/`，并在可用时加载短期 `ugphone_runtime_context.json`。预检会进一步尝试以计划任务等价的 headless persistent profile 验证购买页。

以下情况通常会被视为严重问题：

- 登录状态失效
- 本地登录状态缺失或为空
- UgPhone persistent profile 无法在计划任务/headless 环境恢复
- CAPTCHA / 验证码阻断
- 401 / 403 等访问错误
- 页面被反爬或区域限制完全阻断
- 平台返回 0 条有效产品记录

## 产品记录完整性

产品记录会尽量保留以下信息：

- 平台
- 套餐 / SKU
- Android 版本
- CPU
- RAM
- Storage
- 支持地区
- 购买时长
- 当前价格
- 订阅模式
- 库存 / 可售状态

无法确认的字段应留空或标记为未知，不应猜测补全。

## 当前值与历史值

系统区分：

- `current_observed`：本轮真实采集
- `carry_forward`：沿用最近一次真实观测
- `baseline_reference`：baseline 参考
- 其他不可售、下架、不适用或未知状态

临时采集缺失不会自动等同于下架。

## 部分覆盖

如果一个平台仍有有效数据，但某些套餐、Android 版本或地区本轮未完整采集，通常记录为覆盖不足或警告。

这类情况与以下严重故障不同：

- 平台完全无记录
- 登录/认证失败
- 数据文件损坏
- 历史文件无法解析

## Dashboard 数据检查

生成 Dashboard 时会检查关键数据文件是否存在并可解析，包括：

- 价格概览
- 配对矩阵
- 同周期价格比较
- 价格趋势
- 商品文本变化
- 指标定义
- 调度/平台状态

长期历史可使用 gzip 压缩文件保存。压缩文件必须能够正常解压并解析为 JSON。

## Redfinger 特殊校验

Redfinger 价格 SKU 必须来自有效价格接口，或同时包含价格与购买时长的可见套餐卡片。

以下内容不能单独作为产品价格：

- 游戏推荐
- 钱包余额
- 导航文字
- 加载骨架
- 只有套餐名称而没有价格/时长的元素

## VSPhone 特殊校验

VSPhone 采集订阅和非订阅价格时：

- 数量保持为 1
- 读取套餐卡价格
- 不读取订单页总计
- 不点击最终创建/下单按钮
- 非订阅模式仅采集支持的购买周期

## 安全原则

系统不应为了获取价格而执行：

- 下单
- 支付
- 创建实例
- 自动续费确认
- 购买确认

任何可能产生真实交易的按钮都不属于正常采集流程。
