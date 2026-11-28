# ADR 0026：模型网关一致性服务器（真实 HTTP，非厂商验收）

- 状态：Accepted（传输层与失败路径已用真实 socket 验证；厂商语义仍未验证）
- 日期：2026-11-28
- 相关代码：`backend/tools/openai_conformance_server.py`、`backend/tests/test_agent_model_conformance.py`

## 问题

M5 的模型网关此前只有 `httpx.MockTransport` 测试。MockTransport 直接返回对象，绕过了 chunked 编码、逐行切分、半包/粘包、读超时和连接中断，而这些正是流式客户端最容易出错的地方。没有真实供应商密钥时，无法做厂商端到端，但这不等于只能接受 Mock。

## 决定

提供一个本地 OpenAI 兼容一致性服务器，用 `ThreadingHTTPServer` 在 127.0.0.1 上真实监听，按 wire 协议输出：

- `data:` 分帧、`choices[].delta.content` 逐字增量、`finish_reason`、`usage`（可选缺失）、`[DONE]`；
- 工具调用按 index 分片，`arguments` 跨帧拼接；
- 故障注入：`rate_limit`（前 N 次 429 后成功）、`server_error`（500）、`slow`（超过读超时）、`bad_request`、`no_usage`、`bad_tool`（非白名单工具名）。

测试用生产客户端（`stream_provider` + 真实 `httpx.AsyncClient`）连它，断言：

- 文本增量拼回完整回答，usage 与 `usage_known` 正确；
- 无 usage 时标记 `usage_known=false`，不伪装成 0 成本；
- 工具分片拼装完整、非白名单工具被丢弃并给出 `tool_not_allowed`；
- 429 重试后成功；持续 429 以 `model_unavailable/rate_limit` fail closed；
- 500 归为 `upstream_error`，读超时归为 `timeout`；
- 缺 API key 在发请求前就拒绝。

服务器也可手动启动，把 `AI_BASE_URL` 指过去做交互调试。

## 这条证据能证明什么、不能证明什么

能证明：我们的客户端在真实 HTTP/SSE 语义下能正确解析、重试、超时与失败关闭。

不能证明：DeepSeek/OpenAI 的真实输出形状、限流策略、计费与账单、长上下文下的分片行为。厂商端到端仍是明确缺口，文档与 ADR 都不写成"已通过真实供应商验收"。

## 回滚

删除 `tools/openai_conformance_server.py` 与对应测试即可；生产代码零改动。
