# 教程合成夹具

给 [03 解析层](../../../tutorials/03-解析层.md) 的两级去重实验用。全部是虚构材料，不含真实个人资料。

| 文件 | 用途 |
| --- | --- |
| `make_docx.py` | 用 **Python 标准库**生成下面两个 DOCX（手搓最小 OOXML，生成端零依赖）。 |
| `demo-a.docx` | 标题「演示 A」，正文含共享段落。 |
| `demo-b.docx` | 标题「演示 B」，正文含**逐字节相同**的共享段落。 |

两份 DOCX 字节不同（所以是两份 SourceDocument），但含同一段正文（所以共享一条 Evidence）。这正是实验要观察的现象。

重新生成：

```bash
python3 examples/tutorials/fixtures/make_docx.py
```

> 服务端解析 DOCX 依赖 `python-docx`（已在 `backend/pyproject.toml`），与"生成端只用标准库"是两回事。上传用 `POST /api/v1/evidence/file`（multipart/form-data），详见 [03 篇观察 3](../../../tutorials/03-解析层.md#观察-3：用两份合成-docx，亲手验证两级去重)。
