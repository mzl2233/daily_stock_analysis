# openclaw / 微信 ClawBot 集成指南

本文档说明如何通过 [openclaw](https://github.com/openclaw/openclaw) 或微信 ClawBot 调用 daily_stock_analysis（DSA）API，实现“用户发文本 -> DSA 分析或 Agent 问答 -> 返回简洁文本”的闭环。

## 推荐接入路径

优先使用新的 ClawBot 适配层：

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/v1/clawbot/message` | POST | 推荐入口。接收自然语言文本，自动路由到同步分析或 Agent，并返回可直接回复给微信的纯文本 |
| `/api/v1/analysis/analyze` | POST | 原始分析 API，适合你想自己处理结构化报告时使用 |
| `/api/v1/agent/chat` | POST | 原始 Agent API，适合你想自己维护多轮会话与策略路由时使用 |
| `/api/health` | GET | 健康检查 |

## 前置条件

1. DSA 服务已运行：`python main.py --serve-only`
2. ClawBot 侧具备 HTTP 调用能力
3. GitHub Actions 仅适合定时任务，不适合作为长期对外 API 服务

## `/api/v1/clawbot/message` 请求格式

```json
{
  "message": "帮我分析贵州茅台",
  "mode": "auto",
  "user_id": "wx-user-001",
  "report_type": "detailed",
  "force_refresh": false,
  "notify": false
}
```

字段说明：

- `message`：必填，ClawBot 收到的原始文本
- `mode`：
  - `auto`：优先识别股票并走同步分析；未识别到股票时，若 Agent 可用则回退到 Agent
  - `analysis`：只走同步分析；未识别股票时返回 `unresolved_stock`
  - `agent`：只走 Agent；若 Agent 未开启则返回 `agent_unavailable`
- `user_id`：可选，用于生成稳定的 Agent `session_id`
- `session_id`：可选，显式覆盖会话 ID
- `stock_code`：可选；若 ClawBot 已自行提取股票代码，可直接传入
- `report_type`：`simple` / `detailed` / `full` / `brief`
- `force_refresh`：是否强制刷新
- `notify`：是否复用现有通知渠道发送推送；首版默认建议为 `false`
- `skills` / `context`：仅在 `agent` 模式下按需传入

## 返回示例

### 1. 分析模式

```json
{
  "success": true,
  "mode": "analysis",
  "text": "贵州茅台（600519）\n操作建议：持有\n趋势判断：看多\n情绪评分：78\n摘要：趋势保持强势，回调可分批关注。\n关键点位：理想买点 1820；止损 1760；止盈 1950",
  "query_id": "query_clawbot_001",
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "session_id": null
}
```

### 2. Agent 模式

```json
{
  "success": true,
  "mode": "agent",
  "text": "缠论视角下 600519 当前更适合等回踩确认。",
  "session_id": "clawbot_wx-user-001",
  "query_id": null,
  "stock_code": null,
  "stock_name": null
}
```

## 错误响应格式

ClawBot 适配层统一返回平铺结构，便于机器人侧直接判断：

```json
{
  "error": "agent_unavailable",
  "message": "Agent 模式未开启或未配置可用模型",
  "detail": {
    "source": "agent",
    "mode": "agent"
  }
}
```

常见错误：

| 状态码 | error | 说明 |
|--------|-------|------|
| 422 / 400 | `validation_error` | 请求体缺字段时返回 422；`message` 为空或仅空白字符时返回 400 |
| 400 | `unresolved_stock` | `analysis` 模式下未识别到股票代码/名称 |
| 400 | `agent_unavailable` | `agent` 模式下 Agent 未开启或未配置可用模型 |
| 400 | `unsupported_request` | `auto` 模式下既未识别股票，又无法回退 Agent |
| 500 | `analysis_failed` / `internal_error` / `agent_failed` | 下游分析或 Agent 执行失败 |

## 股票输入说明

ClawBot 适配层会优先复用仓库现有解析能力，支持：

- A 股代码：`600519`、`000001`
- 港股代码：`hk00700`、`00700.HK`
- 美股代码：`AAPL`、`TSLA`、`BRK.B`
- 中文股票名：如 `贵州茅台`、`腾讯控股`

这意味着首版接入不必在 ClawBot 侧自己维护一套名称到代码的映射。

## openclaw 配置示例

在 `~/.openclaw/openclaw.json` 中配置：

```json
{
  "skills": {
    "entries": {
      "daily-stock-analysis": {
        "enabled": true,
        "env": {
          "DSA_BASE_URL": "http://localhost:8000"
        }
      }
    }
  }
}
```

## 推荐 SKILL.md 示例

将以下内容保存到 `~/.openclaw/skills/daily-stock-analysis/SKILL.md`：

```markdown
---
name: daily-stock-analysis
description: 调用 daily_stock_analysis 的 ClawBot 适配 API，支持股票分析与 Agent 问答的文本闭环。
metadata:
  {"openclaw": {"requires": {"env": ["DSA_BASE_URL"]}, "primaryEnv": "DSA_BASE_URL"}}
---

## 触发条件

当用户询问股票分析、趋势判断、买卖建议或策略问股时使用。

## 工作流程

1. 判断消息类型：
   - 明确是“分析某只股票”时，用 `mode=analysis` 或 `mode=auto`
   - 明确是“缠论/均线/波浪等策略问答”或需要多轮上下文时，用 `mode=agent`
2. 调用 `{DSA_BASE_URL}/api/v1/clawbot/message`
3. 将返回的 `text` 原样回复给用户
4. 若返回 `error/message/detail`，将 `message` 反馈给用户，并保留 `detail` 便于排障

## 请求示例

分析：
```json
{"message":"帮我分析贵州茅台","mode":"analysis","user_id":"wx-user-001"}
```

策略问股：
```json
{"message":"用缠论分析 600519","mode":"agent","user_id":"wx-user-001"}
```
```

## 何时直接调用原始 API

若你需要以下能力，可以跳过 ClawBot 适配层，直接调用原始接口：

- 需要完整结构化报告：用 `/api/v1/analysis/analyze`
- 需要自己维护多轮上下文或技能路由：用 `/api/v1/agent/chat`
- 需要异步任务与状态轮询：用 `/api/v1/analysis/analyze` + `/api/v1/analysis/status/{task_id}`

## 故障排查

| 现象 | 可能原因 | 处理建议 |
|------|----------|----------|
| 连接失败 | DSA 未运行、端口错误、防火墙 | 确认 `python main.py --serve-only` 已启动，检查 `DSA_BASE_URL` |
| `unresolved_stock` | 文本里未识别到股票名/代码 | 在 ClawBot 侧补充更明确的问题，或显式传 `stock_code` |
| `agent_unavailable` | Agent 未开启或无可用模型 | 检查 `AGENT_MODE` 与 Agent 模型配置 |
| 500 错误 | AI 配置、数据源或网络问题 | 查看 DSA 服务日志定位下游失败点 |
| 同步分析耗时长 | 使用了同步分析路径 | 增加 HTTP 超时；如需更复杂编排，可直接调用原始异步分析 API |

## 认证说明

默认情况下 DSA API 无需认证。若启用了 `ADMIN_AUTH_ENABLED=true`，则 ClawBot 调用时需携带登录后获得的 Cookie；当前 API 不支持 Bearer Token。
