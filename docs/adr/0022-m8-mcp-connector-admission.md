# ADR 0022：M8 MCP 受控接入——准入策略层

- 状态：Accepted（准入策略层已实现；隔离执行与网络策略未做，需 OS 沙箱）
- 日期：2026-11-28
- 相关契约：[`agent-mcp-connector-v1.json`](../../contracts/agent-mcp-connector-v1.json)
- 相关代码：`backend/app/runtime/agent/mcp_connectors.py`、`backend/app/api/routes/agent_mcp.py`

## 决定

把"MCP 受控接入"拆成两层：**准入策略层**（本 ADR 实现）与**隔离执行层**（未实现，OS 沙箱前置）。

准入层是一个 connector 注册表：每条记录保存命名空间、工具白名单、所需 scope，以及对这份配置的 SHA256 指纹。它遵循 V4 的默认 deny：connector 注册后是 `registered`（非启用），启用是独立显式动作；`admit()` 只在"已启用且未撤销 + 配置指纹匹配 + 工具名带正确命名空间前缀且在白名单 + 调用方 scope 足够"时放行，否则给出具体拒绝码。显式 deny（撤销）优先，撤销立即禁用。

关键边界：**这个模块不连接任何 MCP server、不发网络请求、不加载第三方代码进 daemon 或 CLI**。它是纯策略判定。CareerLens 现有的对外 MCP server（`backend/app/mcp/server.py`）是另一回事：它暴露职业库只读/写入工具，仍按 read/write/manage scope 鉴权；connector 不会自动获得 manage 权限。

### 执行接线（受控网关）

网关 `internal/agent/tools/invoke` 对带 connector 命名空间的工具名（如 `docs.search`）不再查内置工具表，而是走 `mcp_execution.execute()`：按 capability 的可信 user_id 查 connector → `admit()` 判定 → 未准入返回具体拒绝码；即便准入，也因没有经审核的执行器与 OS 沙箱而返回结构化 `execution_unavailable`，**fail closed**，绝不假装执行成功或退化成内置工具。这让"MCP 工具必须经过准入"成为真实执行路径，同时不越过无沙箱红线。

调用方 scope 不从模型或请求体读取：绑定令牌的 run 以该令牌 `scopes` 为上限（只读令牌无法访问 write/manage connector）；无令牌的本地 CLI 会话视为用户本人操作，保留其自有 connector 的完整 scope。

## 为什么不全量实现执行器

V4 要求 MCP 执行器在经验证的 AppContainer 或等效受限 token + ACL/网络策略中运行，且"MCP 网络访问默认 deny，按服务器配置审核"。本机 AppContainer 原型只证明了文件写拒绝/读允许，**网络隔离、第三方代码加载、Node/Python 兼容性均未验证**。在无沙箱时引入外部 MCP 客户端会让"默认 deny"沦为空话，并违反"不得把任意第三方代码加载进 daemon"。因此先冻结准入契约与服务端强制，执行器留到沙箱验证后，不冒进宣称合规。

## 验证

- 注册后状态为 `registered`，`admit()` 返回 `connector_disabled`。
- 启用后：命名空间不匹配 → `namespace_mismatch`；白名单外工具 → `tool_not_allowed`；scope 不足 → `scope_insufficient`；配置指纹不匹配 → `config_digest_mismatch`。
- 撤销后状态转 `disabled` 且 `admit()` 恒拒绝；已撤销 connector 不能重新启用。
- 网关对 `docs.search` 走受控执行：未注册/禁用 → 具体拒绝码；准入但无执行器 → `execution_unavailable`；不会落到内置工具表。
- 网关的调用方 scope 取自 run 的绑定令牌：`write` 令牌访问 `manage` connector 返回 `scope_insufficient`，模型无法自报 scope 提权。
- 迁移 `a9b0c1d2e3f4` 建立 connector 表，head 一致。

## 未做与边界

- 没有外部 MCP 客户端、stdio/HTTP 传输、第三方 connector 代码加载。
- 没有网络 deny 策略、AppContainer 内启动 CLI/MCP、完整攻击矩阵（T16）。
- 准入已接入网关执行路径，但**没有真实执行器**：已准入工具一律 fail closed 返回 `execution_unavailable`。不声称 MCP 工具可实际运行。

## 回滚

删除本 ADR、契约、`agent_mcp_connectors` 表及迁移、准入 API/服务即可；不影响现有职业库 MCP server 与 Agent 工具链。
