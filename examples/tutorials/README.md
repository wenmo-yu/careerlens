# 最小示例脚本

四个用 **Python 标准库**写的脚本，各自只演示一个机制。它们调用本机运行中的 CareerLens Demo API，**不导入生产后端模块、不需要第三方依赖、不需要 API Key**。

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
| [lesson-03-chat-modes](lesson-03-chat-modes/) | 同一问题切三种模式，看诊断与引用 | [04 检索 Agent](../../tutorials/04-retrieval-agent.md) |
| [lesson-04-events](lesson-04-events/) | 提交任务、带超时轮询事件，核对终态与序号 | [06 运行时](../../tutorials/06-runtime.md) |

## 约定

- 固定使用**专用教学用户**（`lesson-*` 前缀），不碰你的真实资料。
- 所有内容都是合成材料，**不向外部服务发送任何数据**——只请求 `localhost`。
- 每个脚本自带退出码：断言失败返回非 0，方便你判断「跑对了没有」。
- 输出里 ID、分数等是运行时生成的，脚本只校验「结构正确 / 关系成立」，不比对固定字符串。

想留着这些数据？默认会保留在 Demo 库里，用工作台的隐私区删除即可。
