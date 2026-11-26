# 教程合成夹具

下面是教程使用的合成材料。

| 文件 | 用途 |
| --- | --- |
| `make_docx.py` | 用 **Python 标准库**生成下面两个 DOCX（手搓最小 OOXML，生成端零依赖）。 |
| [demo-a.docx](demo-a.docx) | 标题「演示 A」，正文含共享段落。 |
| [demo-b.docx](demo-b.docx) | 标题「演示 B」，正文含相同的共享段落。 |
| [hy4-lin-api.html](hy4-lin-api.html) | 作业正文连同一段会被解析器跳过的脚本标记。供[第 10 篇](../../../tutorials/10-导入与可回查画像.md)做导入与证据回查。 |

两份 DOCX 字节不同（所以是两份 SourceDocument），但含同一段正文（所以共享一条 Evidence）。这正是实验要观察的现象。

重新生成：

```bash
python3 examples/tutorials/fixtures/make_docx.py
```

服务端用 `python-docx` 解析标题和段落。到 [03 篇 DOCX 实验](../../../tutorials/03-解析层.md#实验-验证-docx-两级去重) 上传两个文件，在返回的 `items` 中按正文比对证据 ID。
