# CareerLens Evaluation

评测集由人工标注，不调用 LLM 充当裁判。当前指标：

- `Profile Extraction F1`：预测的 `(category, name)` 与人工画像标签的微平均 F1。
- `Evidence Recall@K`：每个检索问题的标注 Evidence 在 Top-K 中的平均召回率。
- `Supported Claim Rate`：预测画像中，能够在有效 Evidence ID 对应原文里找到直接别名证据的比例。
- `Requirement Matching F1`：`(skill, strong/partial/gap)` 与人工 JD 标签的微平均 F1。

仓库提供两套内置数据：

- `backend/app/evaluation/sample_dataset.json`：1 个场景的链路冒烟样本。
- `backend/app/evaluation/dev_benchmark_v2.json`：10 个合成场景、40 条 Evidence、20 个检索问题的开发回归集。

v2 覆盖中英文技能别名、strong / partial / gap、纯缺口及无技能干扰样本，并由 CI 和网页质量区默认使用。它用于防止确定性抽取、检索和匹配逻辑回归，不代表真实用户分布。

运行单样本冒烟：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/evaluation/sample
```

运行 v2 开发基准：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/evaluation/regression/benchmark
```

运行自定义数据集：

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/evaluation/run `
  -ContentType application/json `
  -InFile .\eval\datasets\careerlens-baseline-v1.json
```

## 回归门禁

v2 冻结阈值位于 `eval/baselines/careerlens-dev-benchmark-v2.json`。命令成功返回退出码 `0`，任一核心指标低于阈值时返回 `1`，可直接用于 CI：

```powershell
Set-Location backend
python -m app.evaluation.cli `
  --dataset app/evaluation/dev_benchmark_v2.json `
  --baseline ../eval/baselines/careerlens-dev-benchmark-v2.json `
  --output ../eval/results/latest.json
```

API 也支持门禁：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/evaluation/regression/sample
```

阈值应在测试集冻结后由团队评审调整，不能随着一次失败运行自动降低。
