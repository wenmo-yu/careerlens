# ADR 0012：M5 Agent Model Gateway 接入 OpenAI-compatible 流式供应商

- 状态：Accepted（接口冻结；真实供应商端到端未验证）
- 日期：2026-11-28
- 相关代码：`backend/app/core/config.py`、`backend/app/runtime/agent/model.py`、
  `backend/tests/test_agent_gateway.py`
- 相关 ADR：[0010 Agent Runtime Contract](0010-m3-agent-runtime-contract.md)、
  [0011 M4 Runtime Manager](0011-m4-runtime-manager.md)

## 决定

### 1. 自研网关，不引入 OpenAI Agents SDK

`stream_provider(messages, tools, *, provider, script=None, client=None, settings=None)` 是本仓库
自研的异步生成器：HTTP 只用项目已有的 `httpx.AsyncClient`，输出直接复用 M3 的事件契约。
不新增 Agent SDK 依赖，现有 `build_turn`、`stream_turn`、`ModelTurn` 签名保持不变。

### 2. 离线与远程共用一条事件通道

- `demo` / `scripted` 委托 `build_turn` + `stream_turn`，事件形状与 M3 完全一致（不附加新字段）。
- `openai_compatible` / `deepseek` / `local` 走 SSE：
  `POST {ai_base_url}/chat/completions`，`stream=True`，`stream_options={"include_usage": true}`，
  `tool_choice="auto"` 并携带 function schema。
  `response_format={"type":"json_object"}` 只在**没有工具**时发送，避开兼容端点对两者共存的拒绝。
  若供应商忽略 `stream_options`，`usage_known=false`，成本按 0 记录而不编造。
- 配置继承 `ai_base_url / ai_api_key / ai_model / ai_timeout_seconds /
  ai_input_price_per_million / ai_output_price_per_million`，另有 agent 专用覆盖
  `AGENT_MODEL_NAME / TEMPERATURE / MAX_TOKENS / RETRIES / BACKOFF_MS / STREAM_TIMEOUT_SECONDS`。
  `AGENT_MODEL_NAME` 为空时回退 `ai_model`，流超时为 0 时回退 `ai_timeout_seconds`。
- `AGENT_MODEL_PROVIDER` 允许 `demo, scripted, openai_compatible, deepseek, local`；
  前两者不需要密钥，其余要求非空 `AI_API_KEY`（配置校验与流入口各检查一次）。

### 3. 事件契约

| 事件 | 字段 | 时机 |
| --- | --- | --- |
| `delta` | `type`, `text` | 每个 SSE `data:` 帧的 `choices[0].delta.content` 到达即刻发出 |
| `tool_call` | `type`, `id`, `name`, `args` | 仅在流结束后发出；`args` 为完整的 JSON 对象，不发出半截调用 |
| `done` | `type`, `stop_reason`, `usage`, `usage_known`, `provider`, `model` | 唯一结束事件；错误时额外带 `error` 码 |

`stop_reason` 取值：`completed`、`tool_calls`、`invalid_tool_args`、`tool_not_allowed`、
`model_unavailable`。`usage` 恒为 `{"input_tokens": int, "output_tokens": int}`；
供应商未给 usage 时为 0 且 `usage_known=false`。`[DONE]` 帧与多帧 `data:` 拼接均被解析。

### 4. 工具白名单与失败边界

- 非法工具列表（非列表、缺名字、重复名字、parameters 非对象）在联网前 `ValueError` fail loud。
- 超预算 prompt（消息数 > 40 或内容总长 > 60k，与 `MAX_CHARS` 一致）fail loud。
- 模型返回的工具名不在传入的白名单内，或参数是非对象/截断 JSON：
  **不发出任何 `tool_call`**，`done` 用 `tool_not_allowed` / `invalid_tool_args` 结束，
  因此不会执行半截或越权工具。

### 5. 错误与重试

429、5xx、超时、连接错误在**尚未发出任何 delta 前**最多重试 `AGENT_MODEL_RETRIES`（默认 2）次，
指数退避 `AGENT_MODEL_BACKOFF_MS * 2^(n-1)`（默认 250ms 起）。一旦已发出 delta 就不再重放，
避免重复文本；此时同样以 `model_unavailable` 结束。重试耗尽后 yield
`done(stop_reason="model_unavailable", error=<rate_limit|upstream_error|timeout|connection_error>)`，
不向 API 层抛未捕获异常。401/403 与 4xx 不重试。配置类错误（缺 key、超预算、非法工具列表）
保留 `ValueError`，属于调用方契约错误。

### 6. 成本计量

每次 `stream_provider` 调用写一条 `ModelCallMetric`（`operation="agent.stream_provider"`），
字段含 provider / model / status / latency_ms / prompt_tokens / completion_tokens /
`estimated_cost_usd` / error_type / created_at / pricing_configured。价格复用 workflow 的
`ai_*_price_per_million`，usage 未知时成本为 0 且 `pricing_configured=false`。
密钥只进 Authorization 头，不写入 metric、日志或错误事件。

## 替代方案

- **引入 OpenAI Agents SDK**：功能看似对口，但会新增重量级依赖、带来与现有 JSONL/HTTP 契约
  不同的事件形状，且离线 demo/scripted 与故障注入测试更难控制。否决。
- **复用非流式 `LLMProvider.generate_json`**：能少写 SSE 解析，但失去逐字 delta，CLI 的增量
  体验退化，也无法在同一条流里先发文本再发工具意图。否决。
- **把供应商 HTTP 逻辑放进 `agent_internal.py` 路由**：路由将同时承担鉴权、SSE 帧包装与
  供应商协议，难以用 MockTransport 单测。否决；路由层接线留待单独改动。
- **同步 `httpx.Client`**：会阻塞 FastAPI 事件循环。否决。

## 测试命令与真实输出摘要

工作目录 `backend/`，使用项目隔离虚拟环境中的 `python` / `ruff`（命令中的解释器路径按本地环境替换）：

```
python -m pytest tests/test_agent_gateway.py -q
.........................                                                [100%]
25 passed in 1.71s
```

```
ruff check app/core/config.py app/runtime/agent/model.py tests/test_agent_gateway.py
All checks passed!
```

```
python -m pytest -q
........................................................................ [ 19%]
... (略) ...
379 passed, 3 skipped in 115.42s (0:01:55)
```

本次新增 11 个 gateway 测试（文件现共 25 个，其余由并行改动加入），覆盖：demo/scripted 兼容、远程文本流与 usage、
工具调用分片累积、非法工具 JSON、未知工具名、429 重试成功、重试耗尽、缺失 usage、
prompt 预算与非法工具列表、缺少密钥、provider 允许值与密钥校验。
远程用例全部通过 `httpx.MockTransport` 注入假 client，不访问网络。

## 未验证项 / 边界

- **未在真实供应商账号与网络上端到端验证**：所有远程行为只经 MockTransport 验证。
- 真实供应商可能忽略 `stream_options.include_usage`，此时 `usage_known=false`，成本为 0；
  需要供应商侧确认后再做账单核对。
- 未覆盖非标准 SSE 方言（如 `event:` 字段、非 `choices[0]` 结构、非 OpenAI 形状的工具分片）。
- 未做真实账单与 `estimated_cost_usd` 的对账；价格仅来自配置。
- 未验证经过企业代理 / 网关注入认证头时的行为；密钥当前只从 `AI_API_KEY` 读取。
- 内部路由 `/internal/agent/model/complete` 已接到 `stream_provider`；路由级集成由
  `tests/test_agent_cli.py` 的真实 CLI 子进程覆盖，但仍不是真实供应商端到端。
