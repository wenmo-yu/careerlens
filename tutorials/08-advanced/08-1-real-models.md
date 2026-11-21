# 08-1 · 真实模型：什么时候该接，怎么接

**成果**：你能说清默认 Demo 链路与真实模型链路的差别；知道配置项各管什么；能完成一次对照实验，亲眼看到「收藏当作普通文本 vs 兴趣信号」在 Demo 下的不同结果。

**前置**：[01](../01-quickstart.md)、[00-2](../00-foundations/00-2-prompt-and-evidence.md)。**不需要**真实 API Key 就能读完；想实操接入时才需要。

**对应源码**：`backend/app/llm/provider.py`、`backend/app/core/config.py`、`.env.example`。

---

## 两套链路，别混为一谈

| | 默认 Demo 链路 | 真实模型链路 |
| --- | --- | --- |
| 生成 | 确定性 Provider + 规则回退 | DeepSeek / OpenAI-compatible / 本地模型 |
| 检索 | 轻量哈希 Embedding + 词法重排 | 可切 Qdrant + Qwen Embedding / Reranker |
| 要不要 Key | 不要 | 要（或用本地模型） |
| 结果说明 | 证明机制可跑、可复现 | 效果取决于模型和环境，需单独验收 |

**关键提醒**：默认链路的匹配分数是规则权重算出来的，不是录用概率，也不是「真实准确率」。接了真实模型也不代表效果自动变好——必须按[评测口径](08-2-evaluation.md)单独验收。

## 配置项各管什么

`.env.example` 里和模型相关的项：

| 配置 | 作用 | 默认 |
| --- | --- | --- |
| `AI_PROVIDER` | 生成模型来源 | `demo` |
| `AI_BASE_URL` | OpenAI 兼容端点地址 | `https://api.deepseek.com` |
| `AI_API_KEY` | 密钥 | 空 |
| `AI_MODEL` | 默认模型名 | `deepseek-flash` |
| `MODEL_ROLE_BINDINGS` | 按角色指定不同模型 | 空 |
| `RERANK_STAGES_ENABLED` | 是否开启两级重排 | `false` |
| `RERANK_COARSE_TOP_K` / `RERANK_FINE_TOP_K` | 粗排 / 精排条数 | 15 / 5 |

**`AI_PROVIDER` 的合法值只有 `demo` / `deepseek` / `openai_compatible` / `local`——没有 `qwen`。** 这是个常见误解：`qwen` 是 `RETRIEVAL_PROVIDER`（管 Embedding 和 Reranker）的取值。本地 Qwen 作为**生成模型**要通过 `AI_PROVIDER=local` 加 OpenAI 兼容端点接入，不要写 `AI_PROVIDER=qwen`。

`MODEL_ROLE_BINDINGS` 的格式是 `answer=model-a,wiki=model-b,...`，可用角色有 `answer`、`wiki`、`analysis`、`profile`。不绑定的角色回退到 `AI_MODEL`。模型不可用时会自动回退到确定性结果，并在诊断里记录。

**先看源码再配**（`backend/app/llm/provider.py`）：

1. `get_provider()` 按 `AI_PROVIDER` 返回实现：`demo` / `deepseek` / `openai_compatible` / `local`；非 `qwen` 分支走哈希 Embedding（`hash-v1`，维度 384）。
2. `MODEL_ROLE_BINDINGS` 按角色解析，某角色没绑定就用 `AI_MODEL`；调用失败时 `provider_diagnostics` 如实记录 `fallback`，回到确定性结果——所以「接了模型」不等于「每次都用了模型」，要在响应诊断里核实。
3. 重排角色单独配：`RERANK_STAGES_ENABLED` 默认 `false`，只有开启后才是粗排 Top15 → 精排 Top5（`config.py:42-44`）。

> **先预测再验证**：把 `AI_PROVIDER` 设成一个不存在的值会怎样？按源码它会回退而不是崩溃——但诊断里会留下痕迹。改配置后务必看 `model` 诊断字段，别只看回答通顺就以为用了新模型。

> 成本相关：`AI_INPUT_PRICE_PER_MILLION` / `AI_OUTPUT_PRICE_PER_MILLION` 用于估算调用成本并记录到模型指标里，按自己的模型价格设置。别把 Key 提交到 Git——`.env` 已被忽略。

## 对照实验：为什么入门时不制造矛盾

[00-2](../00-foundations/00-2-prompt-and-evidence.md) 教过：**收藏只是兴趣线索，不等于会**。这在真实系统里靠一个叫 `preference_signal` 的标记实现——只有作为浏览器互动记录导入时，收藏才会被排除在技能之外。

现在亲手验证 Demo 的局限。确保服务已启动（默认 Demo 即可，不需要 Key）。

### 实验 A：普通自述文本导入

`POST /api/v1/evidence/text`：

```json
{
  "user_id": "demo-experiment",
  "source_type": "self_statement",
  "source_name": "note",
  "content": "收藏了 Kubernetes 教程"
}
```

然后 `POST /api/v1/profiles/demo-experiment/rebuild`。看画像里**是否出现了 Kubernetes 技能**。

<details>
<summary>预期结果与解释</summary>

默认 Demo 的确定性提取器会按技能别名表命中 `Kubernetes`（别名含 `kubernetes`、`k8s`），把它提成一项技能，而且证据 ID 还指向这条文本。

**为什么？** 因为 `preference_signal` 这个标记只由浏览器采集连接器产生；用 `/evidence/text` 当普通自述导入时没有这个标记，提取器就把它当成「用户自报掌握的技能」。所以默认 Demo 只做关键词演示，不做真实判断。

</details>

### 实验 B：带兴趣标记的导入

工作台的浏览器采集入口（「从个人数据源继续补充证据」）会把点赞 / 收藏 / 关注标为兴趣线索，发布内容按自报处理。用那条路径导入同类内容，画像就不会把它提成技能。

<details>
<summary>两个实验的结论</summary>

- 同一句话，**来源和标记不同，系统拿到的信息就不同**：普通自述 = 声称掌握；带 `preference_signal` 的互动记录 = 只是兴趣。
- 入门阶段讲「收藏不等于会」，是为了让你先建立正确判断；这里看到 Demo 的误认，是为了让你理解**为什么默认链路只能演示机制**。
- 接了真实模型后，画像提取器还有一条提示词明确说「点赞、收藏、关注仅是兴趣线索」，并会再次用 `preference_ids` 过滤。但那属于模型链路，质量仍需单独验收。

</details>

## 自查清单

- [ ] 能说出 Demo 链路和真实模型链路的三点差别
- [ ] 知道 `AI_PROVIDER` 没有 `qwen` 这个值，本地 Qwen 怎么接
- [ ] 做完对照实验，能解释「同一句话两种导入结果不同」的原因
- [ ] 能说清为什么评测分数不等于真实准确率

## 常见坑

- **把 Key 提交到 Git**：`.env` 已忽略，不要手动加进版本控制。
- **写 `AI_PROVIDER=qwen`**：错，qwen 属于 `RETRIEVAL_PROVIDER`。
- **以为接了模型就不用评测**：恰恰相反，更要在合成集和授权样本上单独验收。

## 下一步

继续 [08-2 · 评测口径](08-2-evaluation.md)，学会正确解读那些分数。术语见[术语表](../GLOSSARY.md)。
