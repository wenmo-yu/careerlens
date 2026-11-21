# 最小示例脚本

五个用 **Python 标准库**写的脚本，各自只演示一个机制。其中四个调用本机运行中的 CareerLens Demo API，**不导入生产后端模块、不需要第三方依赖、不需要 API Key**；第五个（lesson-05）纯离线手算，连服务都不用开。

先按 [01 快速开始](../../tutorials/01-quickstart.md) 把服务跑起来（默认 Compose，`AUTH_MODE=disabled`），再回来跑脚本。

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

每个脚本都可以带一个可选参数指定服务地址，默认是 `http://localhost:8000`：

```bash
python3 examples/tutorials/lesson-01-evidence/main.py http://localhost:8000
```

> 没装 Python？见 [Python 选做准备](../../tutorials/setup/python-basics.md)。

## 四个例子

| 例子 | 核对什么（不背固定输出） | 对应课程 |
| --- | --- | --- |
| [lesson-01-evidence](lesson-01-evidence/) | 写入一条合成自述，打印非空 Evidence ID | [03 解析层](../../tutorials/03-parsing.md) |
| [lesson-02-dedup](lesson-02-dedup/) | 同用户导入两次比对 ID；不同用户不复用 | [03 解析层](../../tutorials/03-parsing.md) |
| [lesson-03-chat-modes](lesson-03-chat-modes/) | 比较三种检索模式，核对实际命中和原始证据 | [04 检索 Agent](../../tutorials/04-retrieval-agent.md) |
| [lesson-04-events](lesson-04-events/) | 同键返回同一任务；验证成功结果与事件；可跑缺画像负例 | [06 运行时](../../tutorials/06-runtime.md) |
| [lesson-05-rrf](lesson-05-rrf/) | 离线手算排名融合；改变量、名次交错、榜首判错（不用开服务） | [04 样板课](../../tutorials/04-retrieval-agent.md) |

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
