# ADR 0022：M8 MCP 受控接入——准入策略层

- 状态：Accepted（准入策略层已实现；隔离执行与网络策略未做，需 OS 沙箱）
- 日期：2026-11-28
- 相关契约：[`agent-mcp-connector-v1.json`](../../contracts/agent-mcp-connector-v1.json)
- 相关代码：`backend/app/runtime/agent/mcp_connectors.py`、`backend/app/api/routes/agent_mcp.py`

## 决定

把"MCP 受控接入"拆成两层：**准入策略层**（本 ADR 实现）与**隔离执行层**（未实现，OS 沙箱前置）。

准入层是一个 connector 注册表：每条记录保存命名空间、工具白名单、所需 scope，以及对这份配置的 SHA256 指纹。它遵循 V4 的默认 deny：connector 注册后是 `registered`（非启用），启用是独立显式动作；`admit()` 只在"已启用且未撤销 + 配置指纹匹配 + 工具名带正确命名空间前缀且在白名单 + 调用方 scope 足够"时放行，否则给出具体拒绝码。显式 deny（撤销）优先，撤销立即禁用。

关键边界：**这个模块不连接任何 MCP server、不发网络请求、不加载第三方代码进 daemon 或 CLI**。它是纯策略判定，同时提供给"未来的受控 connector 网关"使用。CareerLens 现有的对外 MCP server（`backend/app/mcp/server.py`）是另一回事：它暴露职业库只读/写入工具，仍按 read/write/manage scope 鉴权；connector 不会自动获得 manage 权限。

## 为什么不全量实现执行器

V4 要求 MCP 执行器在经验证的 AppContainer 或等效受限 token + ACL/网络策略中运行，且"MCP 网络访问默认 deny，按服务器配置审核"。本机 AppContainer 原型只证明了文件写拒绝/读允许，**网络隔离、第三方代码加载、Node/Python 兼容性均未验证**。在无沙箱时引入外部 MCP 客户端会让"默认 deny"沦为空话，并违反"不得把任意第三方代码加载进 daemon"。因此先冻结准入契约与服务端强制，执行器留到沙箱验证后，不冒进宣称合规。

## 验证

- 注册后状态为 `registered`，`admit()` 返回 `connector_disabled`。
- 启用后：命名空间不匹配 → `namespace_mismatch`；白名单外工具 → `tool_not_allowed`；scope 不足 → `scope_insufficient`；配置指纹不匹配 → `config_digest_mismatch`。
- 撤销后状态转 `disabled` 且 `admit()` 恒拒绝；已撤销 connector 不能重新启用。
- 迁移 `a9b0c1d2e3f4` 建立 connector 表，head 一致。

## 未做与边界

- 没有外部 MCP 客户端、stdio/HTTP 传输、第三方 connector 代码加载。
- 没有网络 deny 策略、AppContainer 内启动 CLI/MCP、完整攻击矩阵（T16）。
- 没有 connector 与 Agent 工具注册表的运行时接线；当前 `admit()` 是准入体检，不参与工具执行。

## 回滚

删除本 ADR、契约、`agent_mcp_connectors` 表及迁移、准入 API/服务即可；不影响现有职业库 MCP server 与 Agent 工具链。
