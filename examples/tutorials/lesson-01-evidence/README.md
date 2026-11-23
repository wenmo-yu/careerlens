# 练习 01 · 写入证据

**对应课程**：[03 解析层](../../../tutorials/03-解析层.md)
**核对什么**：写入一条合成自述，拿到非空 Evidence ID。

## 运行

先确保服务已启动，然后：

```bash
python3 examples/tutorials/lesson-01-evidence/main.py
```

## 预期输出

```text
HTTP 201，count=1
返回的证据 ID：<一串 ID>
来源类型：self_statement
OK：拿到非空 Evidence ID。
```

脚本只校验「返回 201、拿到非空 ID、内容对得上」，不比对固定 ID 字符串。同一教学用户重跑时会复用证据，响应仍是 201；验证去重见[练习 02](../lesson-02-dedup/)。

## 它做了什么

`POST /api/v1/evidence/text`，请求体里 `user_id` 用专用教学用户，`source_type` 是 `self_statement`。返回结构是 `{"items": [...], "count": N}`，ID 取 `items[0].id`。

## 清理

数据留在 Demo 库里。要删就用工作台隐私区的「删除 Evidence」，输入打印出的 ID。
