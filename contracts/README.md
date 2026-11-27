# CareerLens 版本化契约

本目录保存跨进程、跨端和跨版本的机器可读契约。它是 V4 实施的稳定接口基线；实现代码必须服从契约，不能先用私有结构实现再倒推文档。

| 契约 | 当前版本 | 用途 |
| --- | --- | --- |
| [`openapi-v0.4.0.json`](openapi-v0.4.0.json) | OpenAPI 3.1.0 / API 0.4.0 | 从当前 FastAPI 应用直接导出的完整 API 快照 |
| [`api-baseline-v0.4.0.json`](api-baseline-v0.4.0.json) | baseline schema 1 | 路径、方法、operationId、标签和兼容规则清单 |
| [`runtime-jsonl-v1.schema.json`](runtime-jsonl-v1.schema.json) | Runtime JSONL v1 | Scheduler ↔ CLI 的双向 RPC 帧契约 |
| [`runtime-jsonl-v1.examples.jsonl`](runtime-jsonl-v1.examples.jsonl) | Runtime JSONL v1 | request、response、event 的边界样例 |
| [`runtime-jsonl-v1.methods.json`](runtime-jsonl-v1.methods.json) | Runtime JSONL v1 | 方法注册表、方向与 id 空间、错误码与可重试位 |
| [`daemon-control-v1.json`](daemon-control-v1.json) | Daemon Control v1 | 本机管道控制面：握手、命令、错误码与 ACL 要求 |

## 当前基线事实

- 生成提交：`91cfae2278123cdaf9bd82a1a89403f731c846e7`。
- 与 V4 设计基线 `43c67d3b01540ba80c00c17efd483336a08c2426` 的 `backend/`、`frontend/`、`docs/` 子树对象 ID 相同；两者之间只有教程文档提交。
- OpenAPI 快照包含 79 个路径、88 个操作和 78 个 schema。
- Runtime JSONL 是 CareerLens 自定义协议：不兼容 ACP，不使用 Pi 的事件名、方法名或会话结构，也不把 JSONL 日志当作业务事实来源。

## 兼容规则

1. 在 M0–M9 中，现有 API method/path、必填请求字段、成功状态码和 Run SSE 游标语义只可新增兼容字段，不可静默改变。
2. 破坏性 API 变化必须先提 ADR、提升 API 版本并更新本目录快照；前端和 Desktop 不允许根据假接口先行开发。
3. Runtime 帧采用 `v` 字段版本化。v1 已冻结帧 envelope、请求/响应关联、事件字段与方法注册表（见 `runtime-jsonl-v1.methods.json`）；能力协商、消息上限、超时与背压参数仍属待测项。
4. 请求 ACK 只表示接收，`settled` 表示 Core 产生结果，只有业务库事务提交后的 `committed` 才是 UI 最终成功。

## 重新生成 API 快照

在 `backend/` 下激活已安装依赖的 Python 环境：

```bash
python - <<'PY'
import json
from pathlib import Path
from app.main import app
schema = app.openapi()
Path("../contracts/openapi-v0.4.0.json").write_text(
    json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
```

重新生成后必须核对 API 基线清单和 ADR；不要只覆盖文件而不解释差异。
