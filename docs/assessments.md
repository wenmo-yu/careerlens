# 测评题库：许可、计分与边界

这一页回答三个问题：题目从哪来、分数怎么算、结果能用来做什么。结论先说：**我们只使用可自行编写或公有领域的构念，不复制官方或商业题库**；所有量表都是探索性自评，不是官方测评，也不进入岗位匹配分。

## 1. 为什么不是「官方 MBTI / O*NET 原题」

| 来源 | 许可事实 | 我们的处理 |
| --- | --- | --- |
| IPIP（International Personality Item Pool） | 题库为公有领域，可自由使用、改写与商用；[ipip.ori.org](https://ipip.ori.org/) 与 [IPIP-NEO 使用条款](https://ipipneo.com/zh/terms) 都说明题库与在其上搭建的量表对任何人开放 | **采用其五因素构念**，中文题目自写；未整段搬运英文原题，避免翻译质量与版本漂移 |
| O*NET Interest Profiler | 美国劳工部以 **CC BY-ND 4.0** 发布 Short Form：允许原样转载并署名，**禁止改编**；翻译属于改编 | **不复制、不翻译**；按其活动陈述的写法自写 48 条中文活动，题目与 O*NET 不逐条对应 |
| OEJTS 1.2（Open Psychometrics） | **CC BY-NC-SA 4.0**：禁止商业使用、要求相同方式共享 | **不复制**；NC/SA 与本项目 MIT 许可冲突，且会限制商用部署 |
| MBTI® | Myers & Briggs Foundation 的注册商标与版权题库 | **不使用官方题目、不声称官方类型**；四维代码只叫「偏好组合」 |
| 16Personalities、SDS、Strong、NEO-PI-3 等 | 商业版权 | 不复制、不翻译、不摘编 |

因此，`work_style_4d` 与 `riasec_interest` 的题目全部是本项目自写，`big_five_20` 的构念对应 IPIP 的五个因素。三份题库都在 JSON 的 `license.not_used` 字段里写明了没有采用哪些来源，接口会原样返回，前端在结果页展示。

## 2. 三个量表

| ID | 题目 | 维度 | 作答 | 输出 | 许可 |
| --- | --- | --- | --- | --- | --- |
| `work_style_4d` | 32 | 精力方向 E/I、信息获取 S/N、决策方式 T/F、生活节奏 J/P | 1–5 符合度 | 四组百分比、字母组合、清晰度、接近中点提示 | 项目自写 · MIT |
| `riasec_interest` | 48 | R/I/A/S/E/C 六类活动兴趣 | 1–5 意愿 | 六维 0–100 位置、前三代码、一致性、分化度、方向线索 | 项目自写 · MIT |
| `big_five_20` | 20 | 开放性、尽责性、外向性、宜人性、情绪敏感性 | 1–5 符合度，含反向题 | 五维 0–100 位置、分档、工作风格提示 | 构念参照 IPIP（公有领域），题目自写 · MIT |

题目与规则分别放在 `backend/app/assessment/data/*.json`，加载时由 `loader.py` 校验：ID 唯一、维度引用存在、每个维度至少 3 题、双极量表每个方向至少 3 题、特质量表必须同时有正向与反向题、许可与免责声明字段齐全。改坏一个字段会直接报错，不会悄悄算出错误分数。

## 3. 计分规则（全部确定性）

**通用**

- 答案必须是整数且在量表范围内；未知题号直接拒绝。
- 至少回答 80% 题目；每个维度至少回答 50%；双极量表的每个方向至少回答 2 题。未答项不插补、不按中性值填充。
- 分数是**量程内位置** `(均值 - 最小值) / (最大值 - 最小值) × 100`，不是常模百分位，也不是人群排名。

**四维偏好**

- 每个方向取已答题目的均值；两个方向均值之差换算成 0–100 的强度。
- 强度 < 10 视为「接近中点」，界面会提示不宜当作固定偏好；四个维度都接近中点时组合显示为「接近中点」，而不是硬凑一个类型。
- 字母只表示本次作答的相对高低，**不是 MBTI 官方类型**，也不做「16 型人格」的衍生断言。

**RIASEC**

- 六维各自取活动意愿均值并换算为 0–100；取最高三项作为代码。
- 一致性看代码内相邻字母在六边形上的跨度：都相邻为「高」，出现跨两格为「中」，更大为「低」。
- 分化度 = 最高分 − 最低分，越高表示兴趣越集中。
- 方向线索只用本地教学目录 `roles.json` 的 `riasec` 字段做重合度匹配，**不是市场结论，也不是能力判断**。

**大五**

- 反向题先按量程翻转（`min + max - 原值`），再取均值。
- 分档：≥70 高、58–69 偏高、43–57 中、31–42 偏低、≤30 低；只有偏高/高/偏低/低才给工作风格提示。

**没有做的事**：没有常模、没有信效度验证、没有单次作答的 α 系数（单人作答算 α 没有统计意义）、没有把分数写进技能覆盖、没有用它调整岗位匹配分。

## 4. 结果存在哪里、能做什么

- 存在 `assessment_results` 表，带 `instrument`、`version`、`answers_json`、`result_json`、`source=self_report`、`consent`、`taken_at`；重复提交保留历史，可逐条删除。
- 画像概览 `GET /profiles/{id}/overview` 的 `assessments` 只回显**每个量表最近一次**的标题、代码与时间，明确标注「不是能力事实」。
- 新结果会把未过期的职业报告标为 stale，提醒重新生成；事实画像与证据不变。
- 导出与注销包含测评结果；删除账号时一并删除。

## 5. 怎么再加一份量表

1. 在 `backend/app/assessment/data/` 新建 `<instrument_id>.json`，文件名必须与 `instrument_id` 一致。
2. 填 `version`、`response_scale`、`license`（含 `items`、`license`、`attribution`、`not_used`）、`disclaimer`、`scoring.type`、`dimensions`、`items`。
3. 跑 `pytest tests/test_assessment_instruments.py`；加载器会拒绝不合规的包。
4. 如果来源受版权限制，只在 `not_used` 里注明，不要把题目放进仓库。

## 6. 参考

- IPIP：<https://ipip.ori.org/>；IPIP-NEO 条款：<https://ipipneo.com/zh/terms>
- O*NET Interest Profiler 与 CC BY-ND 4.0：<https://www.onetcenter.org/IP.html>
- OEJTS 1.2 与 CC BY-NC-SA 4.0：<https://openpsychometrics.org/tests/OEJTS/>
- 霍兰德 RIASEC 模型：Holland, J. L. (1959). A theory of vocational choice.
- 大五与工作行为：McCrae & Costa (1987); Roberts et al. (2007) 的元分析综述。
