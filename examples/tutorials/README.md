# 最小示例脚本

这里有六个练习。01–04 用 Python 标准库调用本机 Demo API。05 用标准库离线算排名。06 离线调用项目的评测代码，需要安装后端 Python 依赖。

跑 01–04 前，先按 [01 第一次跑起来](../../tutorials/01-第一次跑起来.md) 启动默认 Compose（`AUTH_MODE=disabled`）。

## 运行方式

在仓库根目录，用 Python 3.11+：

```powershell
# Windows
py examples/tutorials/lesson-01-evidence/main.py
```

```bash
# macOS / Linux
python3 examples/tutorials/lesson-01-evidence/main.py
```

01–04 可选填服务地址，默认是 `http://localhost:8000`：

```bash
python3 examples/tutorials/lesson-01-evidence/main.py http://localhost:8000
```

没装 Python？先按[准备 Python](../../tutorials/setup/Python准备.md)确认命令能运行。06 用的是已安装项目依赖的解释器，命令见下方。

## 四个联网例子（要先开服务）

| 例子 | 核对什么（不背固定输出） | 对应课程 |
| --- | --- | --- |
| [lesson-01-evidence](lesson-01-evidence/) | 写入一条合成自述，打印非空 Evidence ID | [03 解析层](../../tutorials/03-解析层.md) |
| [lesson-02-dedup](lesson-02-dedup/) | 同用户导入两次比对 ID；不同用户不复用 | [03 解析层](../../tutorials/03-解析层.md) |
| [lesson-03-chat-modes](lesson-03-chat-modes/) | 比较三种检索模式，核对实际命中和原始证据 | [04 检索 Agent](../../tutorials/04-检索Agent.md) |
| [lesson-04-events](lesson-04-events/) | 同键返回同一任务；验证成功结果与事件；可跑缺画像负例 | [06 运行时](../../tutorials/06-后台运行时.md) |

## 两个离线例子

| 例子 | 核对什么 | 对应课程 |
| --- | --- | --- |
| [lesson-05-rrf](lesson-05-rrf/) | 用标准库算排名融合，比对默认、改 k、少一次命中和自定义榜单 | [04 检索](../../tutorials/04-检索Agent.md) |
| [lesson-06-eval](lesson-06-eval/main.py) | 用后端依赖跑两份数据，对照 Top-2 与 Recall@2 | [08-2 评测](../../tutorials/08-advanced/08-2-评测.md) |

```bash
python3 examples/tutorials/lesson-05-rrf/main.py            # 默认回归
python3 examples/tutorials/lesson-05-rrf/main.py --k 10     # 只改 k
python3 examples/tutorials/lesson-05-rrf/main.py --drop-b   # 只移除榜 A 的 B
python3 examples/tutorials/lesson-05-rrf/main.py --rankings "A,X,Y,B" "C,U,V,B"
```

06 沿用[动手准备](../../tutorials/setup/动手准备.md)里的后端 Python。从仓库根运行 `python examples/tutorials/lesson-06-eval/main.py`。预期打印两组召回率 `1.0` 和 `0.5`。

## MCP 与测评的额外练习

- [读取实际报告的 MCP 客户端](read_mcp_report.py)接第 07 课生成的教学报告，按 [07-A](../../tutorials/07-A-MCP服务与ACP对照.md)从工具与资源各读取一次。
- [四维合成答案](fixtures/work-style-neutral.json)与[两维六题量表](fixtures/my_scale.json)供 [09](../../tutorials/09-画像与自陈测评.md)提交与校验。

## 合成夹具

[fixtures/](fixtures/) 提供 03 篇使用的两份合成 DOCX。下载现成文件后即可在 Swagger 上传，也可以自行运行 `python3 examples/tutorials/fixtures/make_docx.py` 生成。

## 约定

- 只使用以 `lesson-` 开头的专用教学用户和合成材料。命令可覆盖 API 地址；只指向自己控制的隔离 Demo，不要使用真实资料、共享服务或生产实例。
- 成功才打印 `OK` 并退出 0；失败返回非零。ID 和事件数按实际返回核对，不把文档占位符当固定字段值。
- 手动例程默认保留数据供回看。可以重跑，不用先删库；要清理时，在工作台隐私区核对并删除对应的**教学用户**，不要选自己的账号。

## 维护者：整组复跑

在独立的默认 Demo Compose 环境中，从仓库根目录运行（Windows 可将 `python3` 换成 `py`）：

```bash
python3 -u examples/tutorials/smoke_check.py http://127.0.0.1:8000
```

这也是 CI 执行的命令。检查数据库与 Qdrant 就绪，在同一批新教学账号上跑四例两轮，不在两轮间清库；检查练习 03 的证据检索确实走 Qdrant，再验证练习 04 缺画像时失败且不打印 `OK`。最后用隐私接口清理本轮专用账号；任何一项不符合预期，整组非零退出。

若用隔离的 SQLite＋本地检索 Demo（API 与 Worker 仍需运行），可加 `--local-demo` 检查脚本行为。这不等于 Compose/PostgreSQL/Qdrant 验收。
