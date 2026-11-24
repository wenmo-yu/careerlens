# 4. 读数据与知识库

林澈在两份文档里写了同一句话：「我用 Python 做过一个课程项目，只在本机演示。」他还整理了一张记录 Docker 启动和健康检查的表。用这三份材料一路追下去，你会写出 CareerLens 的文档解析、证据去重、本地检索和 Wiki 编译关键部分，最后亲手从 Wiki 找回原句和两个文件位置。

| 课程 | 做完能验证什么 |
| --- | --- |
| [02 同一段经历为什么有好几个 ID](../02-数据模型.md) | 从一条画像走到同一证据的两个出处，分清文件、块、证据和 Wiki 页 |
| [03 让 DOCX 变成带位置的块](../03-解析层.md) | 跟写文档解析，先读出标题，再给正文和表格标章节 |
| [03-A 写证据去重与来源合并](03-A-去重与来源.md) | 用 A、B、A 三次上传验证两级去重，再用另一个账号做对照 |
| [04 手算检索排名并核对证据](../04-检索Agent.md) | 手算两张榜单怎样融合，判断榜首证据能支持哪句话 |
| [04-A 写本地检索与索引回查](04-A-检索源码与诊断.md) | 从词频和余弦写到候选排序，实测索引返回的 ID 怎样回查数据库 |
| [05 编译第一张 Wiki 主题页](../05-Wiki知识组织.md) | 从两条原始证据编译一页，读懂 `source_refs`、`chunk_refs` 和版本 |
| [05-A 写短句柄与编译流程](05-A-Wiki编译与引用.md) | 把模型返回的 `c000` 翻译回真实证据 ID，观察未知值和回退 |
| [05-B 写表格行保护](05-B-表格行保护.md) | 计算重复行损失，测试同步编译怎样拒绝丢行 |
| [05-C 写版本、冲突和回滚](05-C-Wiki版本与回滚.md) | 写旧版快照和条件更新，复现同时编辑时的 409，恢复旧内容 |
| [05-D 查 Wiki、比较三种模式并回溯](05-D-Wiki查询与综合验收.md) | 写 Wiki 查询，比较 `rag`、`wiki`、`hybrid`，走完整条查询和回溯路线 |

## 选一种读法

**只用浏览器。** 看各课的例子和可展开源码，先做 ID、排名、重复行和版本的预测，再对照结果。第一课会画出资料经过的每一张表。

**亲手敲。** 先按第三章的说明准备 Python 3.11+ 和后端依赖。终端命令从仓库根执行。第四章会建立一份独立练习副本，默认放在 `.cache/knowledge-practice/backend`，各课都用这一份。练习使用本地 SQLite、Demo 和本地评分，Python 环境装好后即可完成主线。 [准备 Python 和虚拟环境](../01-agent-design/01-A-Agent工作流.md)

## 第一次打开练习

在包含 `backend` 和 `tutorials` 的项目根运行下面两条命令。`new` 会打印练习目录，`check parse` 先检查原始实现和环境，预期看到 `12 passed`。

```bash
python tutorials/04-knowledge-base/lab/kb_practice.py new
python tutorials/04-knowledge-base/lab/kb_practice.py check parse
```

每到一关才执行它的 `open` 命令。按打印的路径打开文件，保留函数签名，用注释提示一段段实现，最后移除会主动抛错的 `raise NotImplementedError`。每节先用一组具体输入讲清该留下哪些值，再给完整实现供核对。`check` 使用仓库现有测试。重复打开同一关可以继续上次的内容。

已存在一份第四章练习时可继续用它。需要另开一份时，在启动器路径后、`new` 前传 `--workspace .cache/knowledge-practice-2`。后续的 `open`、`check`、`serve` 与 `worker` 都在子命令前传回同一个路径。 [练习启动器](lab/kb_practice.py)

## 启动练习 API

到 03-A 第一次上传材料时，另开一个服务终端，切到项目根并使用同一个虚拟环境。默认启动命令如下。保持它运行，原终端继续用来执行 `open` 和 `check`。

```bash
python tutorials/04-knowledge-base/lab/kb_practice.py serve
```

打开 [8030 端口 Swagger](http://127.0.0.1:8030/docs)。第三章若已占用 8030，可以先停它，也可以让第四章用 8031。如果你选择了自定义副本和 8031，两项都传入启动命令。

```bash
python tutorials/04-knowledge-base/lab/kb_practice.py --workspace .cache/knowledge-practice-2 serve --port 8031
```

记下完整启动命令和实际端口。下面各课的链接示范默认 8030，选择 8031 时用 `http://127.0.0.1:8031/docs`。换课时保留同一份 SQLite 数据。涉及重启的步骤先在服务终端按 Ctrl+C，再执行原启动命令。第四章的 HTTP 实验做完后即可关闭服务。

做完 Demo 想试着用模型重写 Wiki 时，可以按第三章的设置填写本章副本的 `backend/.env.model`，在原 `serve` 命令末尾加 `--use-model-config`。 [模型配置课](../01-agent-design/模型配置.md)

从 [02 数据模型](../02-数据模型.md) 开始。先在纸上写下 D-A、D-B 和 E，后面会把它们换成接口给出的真实 ID。
