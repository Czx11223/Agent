# SFT 训练数据集构造

> 基于 `cleaned_dialogue.csv`（49 万条清洗后样本）+ Agent 自身规则逻辑，构造多任务 SFT 微调数据集（JSONL，OpenAI 兼容）+ 评测集扩充到 120 条。

---

## 一、设计背景与关键决策

**关键洞察（已验证）**：`cleaned_dialogue.csv` 的 `doctor_followup` 字段非空 78,446 条、其中含问号 16,854 条，但这些"问号"多为患者提问标题或 rhetorical question（如"治疗慢性前列腺炎到底该吃什么药好？"），并非真正的"医生澄清性追问"。无问号样本则多是科普/处方内容。

**因此不能直接用 `doctor_followup` 作追问 teacher 标签**。本方案改用 **Agent 自身规则逻辑**（`_RULE_QUESTIONS` + `slot_filler` + `dept_map`）作 teacher 生成 assistant 输出，语料仅提供多样化患者输入 + `source_department` 科室 ground truth。

---

## 二、任务类型与采样配比

| 任务 | 输入来源 | teacher 逻辑 | 训练条数 | dev 条数 |
|---|---|---|---|---|
| **ask** | `patient_complaint` 筛长度>10 且命中症状词 | `action=ask`；`question`=按已填槽位选 `_RULE_QUESTIONS` 中下一个缺失项模板；`slots`=`slot_filler` 抽取结果；`comfort`=命中 `SOOTHE_RE` 时注入安抚语 | 7,200 | 800 |
| **report** | `slot_filler` 可抽≥4 要素且 main_symptom+duration 非空 | `action=report`；`question`="已收集足够信息…"；`slots`=全槽位；`recommend_top3` 调本地科室推荐 | 1,072 | 119 |
| **emergency** | 合成（`EMERGENCY_KEYWORDS` × 10 场景模板 + 10 直接场景） | `action=emergency`；`comfort`="请保持冷静"；`question`=`EMERGENCY_TEMPLATE`；`slots`=全空 | 2,700 | 300 |
| **rejected** | 合成（`PRESCRIPTION_WORDS`/`DIAGNOSIS_WORDS` 组合造句） | `action=rejected`；`question`=免责声明；`slots`=全空 | 900 | 100 |
| **合计** | | | **11,872** | **1,319** |

> **report 不足 3,000 的原因**：report 要求 `filled_count(slots) ≥ 4` 且 `main_symptom`+`duration` 均非空，而语料中很多 `patient_complaint` 是简单年龄/性别描述（"本人50男"）或短文本，无法抽到 4 个槽位。**质量优先于数量**，保留满足条件的 1,191 条（含 dev）。

---

## 三、JSONL 单条样例（ask 任务）

```json
{
  "messages": [
    {"role": "system", "content": "<pre_consult_agent.py 的 SYSTEM_PROMPT 原文>"},
    {"role": "user", "content": "{\"当前用户消息\":\"咳嗽三天有点发热\",\"目前已采集槽位\":{},\"任务\":\"请按规则继续追问或生成报告\"}"},
    {"role": "assistant", "content": "{\"action\":\"ask\",\"comfort\":\"\",\"question\":\"请问不适主要集中在哪个部位？\",\"slots\":{\"main_symptom\":\"发热\",\"body_part\":\"\",\"duration\":\"三天\",\"accompanying_symptom\":\"发热\",\"past_history\":\"\",\"allergy_history\":\"\"}}"}
  ]
}
```

- **system**：与 `pre_consult_agent.py::SYSTEM_PROMPT` 原文一致
- **user**：JSON 格式，含 `当前用户消息` + `目前已采集槽位`(空) + `任务`
- **assistant**：JSON 格式，`action`/`comfort`/`question`/`slots` 四字段，与 Agent 输出 schema 一致

---

## 四、评测集（120 条）

按《19_评测集设计与指标》§4 配比，从 49 万保留行分层抽样 + 合成：

| 场景 | 条数 | 来源 |
|---|---|---|
| 普通内科 | 48 | `source_department`∈{消化科,心血管科,呼吸科,神经科,内分泌科,耳鼻喉科} 分层 |
| 骨科/皮肤 | 12 | ∈{骨科,普通外科,皮肤科,风湿免疫科} |
| 残缺输入 | 30 | `patient_complaint` 长度 5~12 |
| 急重症 | 18 | 合成（`EMERGENCY_KEYWORDS` × 场景模板） |
| 安抚/越界 | 12 | 合成含疼痛词 + 越界请求 |
| **合计** | **120** | 急重症占比 15.0% |

字段对齐 `19_评测集` §1：`case_id/category/chief_complaint/expected_slots(JSON)/expected_top3(JSON)/emergency(BOOL)`。

---

## 五、脚本结构

```
语料工程/sft_build/
  config.py            # 路径/采样数/SYSTEM_PROMPT/槽位键/规则常量（与 backend 同步）
  slot_filler.py       # extract_slots(text)->dict[str,str]  基于词表+DURATION_RE
  task_ask.py          # build_ask(n=8000)->list[dict]
  task_report.py       # build_report(n=3000)->list[dict]  含 recommend_top3
  task_emergency.py    # build_emergency(n=3000)->list[dict]  合成
  task_rejected.py     # build_rejected(n=1000)->list[dict]  合成
  build_sft.py         # 主入口：拼接 4 类 + dev 切分 → JSONL
  sample_eval.py       # 评测集扩充 → eval_cases.csv
  validate_jsonl.py    # 5 重质量校验

语料工程/sft_build/output/
  sft_train.jsonl      # 11,872 行（OpenAI 兼容 JSONL）
  sft_dev.jsonl        # 1,319 行
  eval_cases.csv       # 120 条评测用例
  build_report.json    # 各任务采样统计
  validate_train.json  # 训练集校验报告
  validate_dev.json    # 验证集校验报告
```

---

## 六、质量校验（validate_jsonl.py · 5 重）

1. **JSONL 合法性**：`json.loads` 逐行 + `messages` 是 3 元素 system/user/assistant + `assistant` 内容可解析为 JSON
2. **action 合法性**：`action ∈ {ask, emergency, rejected, report}`
3. **slots 完整性**：6 key 全存在（emergency/rejected 允许全空值）
4. **黑名单复核**：`assistant` 内容不得命中 `PRESCRIPTION_WORDS`/`DIAGNOSIS_WORDS`
5. **隐私扫描**：`PII_PATTERNS` 全量扫描 user/assistant，命中即剔除

**校验结果**：训练集 11,872 条 + 验证集 1,319 条 = **13,191 条全部合法**（0 非法）。

---

## 七、复用关系（与 Agent 保持一致）

| SFT 脚本常量 | 来源 | 同步对象 |
|---|---|---|
| `SYSTEM_PROMPT` | `config.py` | `pre_consult_agent.py::SYSTEM_PROMPT` |
| `RULE_QUESTIONS` | `config.py` | `pre_consult_agent.py::_RULE_QUESTIONS` |
| `DURATION_RE` | `config.py` | `pre_consult_agent.py::DURATION_RE` |
| `SOOTHE_RE` | `config.py` | `pre_consult_agent.py::SOOTHE_RE` |
| `EMERGENCY_TEMPLATE` | `config.py` | `pre_consult_agent.py::EMERGENCY_TEMPLATE` |
| `DEPT_KEYWORDS` / `EMERGENCY_KEYWORDS` / `DISCLAIMER` | `config.py` | `dept_map.py` |
| `recommend_top3()` / `is_emergency()` | `task_report.py` 内联 | `dept_map.py` 同逻辑 |
| `PRESCRIPTION_WORDS` / `DIAGNOSIS_WORDS` / `PII_PATTERNS` | `validate_jsonl.py` import | `blacklist.py` |

---

## 八、运行命令

```powershell
cd "d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build"
$env:PYTHONIOENCODING="utf-8"

# 1) 构建 SFT 数据集
python build_sft.py --out output/sft_train.jsonl --dev-out output/sft_dev.jsonl

# 2) 构建评测集
python sample_eval.py --out output/eval_cases.csv

# 3) 质量校验
python validate_jsonl.py --input output/sft_train.jsonl --report output/validate_train.json
python validate_jsonl.py --input output/sft_dev.jsonl --report output/validate_dev.json
```

---

## 九、交付物索引

- **训练数据**：[sft_train.jsonl](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build\output\sft_train.jsonl)（11,872 行）+ [sft_dev.jsonl](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build\output\sft_dev.jsonl)（1,319 行）
- **评测集**：[eval_cases.csv](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build\output\eval_cases.csv)（120 条）
- **构建报告**：[build_report.json](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build\output\build_report.json)
- **校验报告**：[validate_train.json](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build\output\validate_train.json) + [validate_dev.json](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build\output\validate_dev.json)
- **脚本**：[sft_build/](file://d:\peixunwenjian\2026.10.8-2026.10.23\智能问诊导诊Agent_交付物\语料工程\sft_build)（9 个 Python 文件）

---

## 十、后续使用建议

1. **上传到 SiliconFlow 微调平台**：将 `sft_train.jsonl` 作为训练集、`sft_dev.jsonl` 作为验证集，选择 `deepseek-ai/DeepSeek-V3` 作为基座模型，启动 SFT 微调任务。
2. **微调后替换 Agent 调用**：在 `backend/.env` 中将 `LLM_MODEL` 改为微调后的模型 ID，即可让 `pre_consult_agent.py` 调用微调模型替代原始 DeepSeek-V3。
3. **评测集验证效果**：用 `eval_cases.csv` 跑《20_评测脚本核心代码》中的评测脚本，对比微调前后的 4 项指标（追问覆盖率/报告完整率/Top3准确率/响应时间）。
4. **迭代优化**：根据 bad case 回流，补充 task_report 的样本量（当前仅 1,191 条，可扩充症状词表或放宽槽位要求）。
