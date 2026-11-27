# 架构决策记录（ADR）

本目录记录 CareerLens Desktop V4 中不可在编码阶段随意改动的架构决定。每条 ADR 写明选择、替代方案、风险、回滚方式和验证证据。状态为 `Accepted` 只表示设计基线已纳入仓库，不表示该能力已经实现。

| 编号 | 决策 | 状态 | 对应阶段 |
| --- | --- | --- | --- |
| [0001](0001-v4-process-topology-and-ownership.md) | 目标进程拓扑与唯一所有权 | Accepted（设计基线） | M0–M9 |
| [0002](0002-api-compatibility-baseline.md) | API 兼容基线 | Accepted（当前 API 快照） | M0–M3 |
| [0003](0003-runtime-jsonl-protocol-v1.md) | Runtime JSONL v1 自定义协议 | Proposed（帧格式已由 M0 原型验证；方法注册表待 M3） | M0、M3、M4 |
| [0004](0004-m0-scripted-runner-prototype.md) | M0 自研 Runner 原型与验证边界 | Accepted（仅原型结论） | M0、M3 |
| [0005](0005-m0-static-export-packaging-and-job-object.md) | M0 静态导出、Python 打包与 Job Object 边界 | Accepted（仅原型证据） | M0 |

## 优先级

1. V4 规范中的明确决定；
2. 当前仓库的实际契约与测试；两者冲突时先提新 ADR，不能私下改范围；
3. 学习资料中的架构原则；
4. 上游实现细节。

公开文档只记录设计名称和公开链接。本机技术资料的绝对路径、反编译产物及私人研究正文不进入公开仓库。
