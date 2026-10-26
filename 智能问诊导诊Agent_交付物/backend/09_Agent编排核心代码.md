# AgentScope 智能问诊导诊 Agent — 编排核心代码

- 版本：V1.0.0　·　框架：AgentScope 1.x（Python）＋ OpenAI 兼容 LLM
- 人设：**预问诊医助**——只收集症状信息，**严禁诊断、严禁开药**。
- 流水线：**追问 → 槽位填充 → 完成度判断 → 报告生成 → 科室推荐**

> 说明：本文件为可上手的核心代码/编排骨架，基于 AgentScope 1.x 的 `AgentBase / Msg / Memory / pipeline` 体系编写。实际运行可按框架版本微调导入路径与构造方式。

---

## 1. 对话状态流转（状态机）

以会话为中心，每次用户消息驱动一次状态转移：

```
                 ┌──────────── user 首条消息 ────────────┐
                 ▼                                      │
    [INIT]  首轮/新会话                                   │
       │ 主诉缺失                                      │
       ▼                                               │
   [ASKING]  追问中（可多轮） ◄──────────────────────────┘
       │  命中急重症词/语义
       ├──────────────► [EMERGENCY] 急诊提示，停止追问（终态/挂起）
       │  索要诊断/开药/处方 → 拒答 [[REJECTED]]（该轮拒答，会话回到 ASKING）
       ├─ 关键槽位未齐 → 生成下一轮追问 → 回到 ASKING
       └─ 关键槽位齐备 → 
                 ▼
   [REPORT_READY] 生成结构化报告 + 科室推荐 Top3
                 ▼
   [FINISHED] 会话结案
```

**转移规则（一次性判定函数 `route()`）：**

| 前置判定 | 优先级 | 达成 → 目标态 | 说明 |
| --- | --- | --- | --- |
| 急重症识别 | P0 | EMERGENCY | 命中即拦截，最高优先 |
| 越界拒答（诊断/开药） | P0 | REJECTED（单轮） | 拒答后豁免声明，不推进槽位 |
| 情绪识别 | P1 | 安抚后回 ASKING | 安抚再追问 |
| 槽位齐备 | — | REPORT_READY | 生成报告与推荐 |
| 槽位缺失 | — | ASKING（继续追问） | 未收集完成 |

```python
class State(Enum):
    INIT = "init"
    ASKING = "asking"
    EMERGENCY = "emergency"
    REJECTED = "rejected"          # 单轮拒答后回 ASKING
    REPORT_READY = "report_ready"
    FINISHED = "finished"

def route(self, ctx):
    if ctx.emergency_hit:          return State.EMERGENCY
    if ctx.violation_hit:          return State.REJECTED
    if ctx.slots.complete():       return State.REPORT_READY
    return State.ASKING
```

---

## 2. 槽位定义与记忆（Memory + SlotManager）

槽位严格对齐《追问要素清单》：`main_symptom / body_part / duration / accompanying_symptom / past_history / allergy_history`。

```python
from agentscope.agent import AgentBase
from agentscope.message import Msg
from agentscope.memory import Memory
from agentscope.agent.memory import TemporaryMemory

SLOT_KEYS = ["main_symptom", "body_part", "duration",
             "accompanying_symptom", "past_history", "allergy_history"]

EMPTY_SLOT = {k: None for k in SLOT_KEYS}


class PreConsultMemory(TemporaryMemory):
    """在 AgentScope Memory 基础上携带槽位状态与会话上下文快照。"""
    def __init__(self):
        super().__init__()
        self.slots = dict(EMPTY_SLOT)
        self.complaint = ""          # 主诉原文（含部位上下文）
        self.department_hint = ""

    def add_msg(self, msg):
        super().add(msg)

    def hire_messages(self, n=8):   # 返回最近 n 条用于上下文
        return self.get_memory()[-n:]

    def merge_slots(self, updates: dict):
        for k in SLOT_KEYS:
            if updates.get(k):       # 已填槽位被更新时覆盖（后信息优先）
                self.slots[k] = str(updates[k]).strip()

    def complete(self) -> bool:
        require = ["main_symptom", "body_part", "duration",
                   "accompanying_symptom", "past_history", "allergy_history"]
        return all(self.slots.get(k) for k in require)
```

---

## 3. 指代消解核心逻辑（"也是这里疼"）

指代处理分两路：**规约（SIG）规则解析** + **LLM 消解**，先规则后模型，命中即回填缺失槽位。

```python
# 共指关键词：部位(这里/那里/同样位置)、时间(一样/同样/也), 与主诉重复句"还是老样子"
COREFERENCE_KW = ["这里", "那里", "这个位置", "同一个位置", "也", "同样", "一样", "还是"]

REFERENCE_PART = {"这里", "那里", "这个位置", "同一个位置"}
REFERENCE_TIME = {"一样", "同样", "也", "老样子"}


def resolve_coreference(user_text: str, mem: PreConsultMemory) -> tuple[bool, dict]:
    """
    返回 (是否发生指代, 更新后的槽位增量)。
    规则例："也是这里疼"
      - "也/一样/同样" -> 时间/症状沿用主诉
      - "这里/那里"    -> 部位沿用上一次明确表述的部位
    """
    updates = {}
    if not any(k in user_text for k in COREFERENCE_KW):
        return False, updates

    # 1) 时间指代：沿用主诉时间
    if any(k in user_text for k in REFERENCE_TIME):
        if mem.slots["duration"]:
            updates["duration"] = mem.slots["duration"]

    # 2) 部位指代：沿用上次部位（"这里疼"绑定到已填 body_part）
    if any(k in user_text for k in REFERENCE_PART):
        if mem.slots["body_part"]:
            updates["body_part"] = mem.slots["body_part"]

    # 3) 兜底：交给 LLM 在槽位抽取时消解（见 §4）
    return bool(updates), updates


# 用法：
had_coref, coref_updates = resolve_coreference(user_utterance, mem)
if had_coref:
    mem.merge_slots(coref_updates)
```

---

## 4. 槽位填充（LLM 工具调用 + 多轮追问）

采用"函数调用"式槽位抽取：把当前槽位与用户本轮话语交给 LLM，让它输出增量槽位（OpenAI 兼容 function calling）。

```python
from agentscope.prompt import to_openai_chat_msg
from agentscope.service import ServiceToolkit

SLOT_FUNCS = [{
    "type": "function",
    "function": {
        "name": "update_slots",
        "description": "从患者最新表述中抽取并更新预问诊槽位；处理指代与补充。禁止诊断/开药。",
        "parameters": {
            "type": "object",
            "properties": {
                "main_symptom":   {"type": "string", "description": "主要症状,如咳嗽"},
                "body_part":      {"type": "string", "description": "部位,如右侧胸肋"},
                "duration":       {"type": "string", "description": "持续时间,如三天"},
                "accompanying_symptom": {"type": "string", "description": "伴随症状"},
                "past_history":   {"type": "string", "description": "既往史"},
                "allergy_history":{"type": "string", "description": "过敏史"},
            },
            "required": [],
        },
    },
}]


async def extract_slots(model, mem: PreConsultMemory, user_text: str) -> dict:
    """调用 LLM 函数调用能力抽取槽位增量。"""
    history = mem.hire_messages(n=8)
    messages = to_openai_chat_msg(history) + [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"当前已收集槽位：{mem.slots}\n最新患者表述：{user_text}\n请调用 update_slots 更新。"},
    ]
    resp = await model(messages, tools=SLOT_FUNCS)
    tool_call = resp.dict().get("tool_calls") or []
    if tool_call and tool_call[0].function.name == "update_slots":
        import json
        return json.loads(tool_call[0].function.arguments)
    # LLM 未走函数调用 -> 无新增，交由追问流程处理
    return {}
```

**槽位缺失 → 继续追问**：由 `CompletenessJudge` 查缺，缺哪项就取对应追问模板（见《11_话术模板库》），且**轮换引用不同模板避免话术重复**：

```python
class CompletenessJudge:
    MISSING_ROUTER = {
        "main_symptom":        "ask_symptom",
        "body_part":           "ask_part",
        "duration":            "ask_duration",
        "accompanying_symptom":"ask_accompany",
        "past_history":        "ask_history",
        "allergy_history":     "ask_allergy",
    }

    def next_missing(self, mem: PreConsultMemory) -> str | None:
        for k in SLOT_KEYS:
            if not mem.slots.get(k):
                return k
        return None
```

---

## 5. 急重症 / 情绪 / 越界 前置识别

```python
EMERGENCY_WORDS = ["胸痛", "呼吸困难", "喘不上气", "大出血", "剧烈腹痛",
                   "晕厥", "意识不清", "过敏性休克", "持续吐血", "剧痛难忍"]

VIOLATION_WORDS = ["诊断", "确诊", "建议用药", "开个药", "处方", "吃什么药",
                   "用药剂量", "化疗", "手术方案", "给我诊断"]

EMOTION_WORDS = {"焦虑": "anxious", "紧张": "anxious", "害怕": "fear",
                 "很痛": "pain", "疼得厉害": "pain", "难受": "distress",
                 "吓死": "fear", "担心": "anxious"}


def detect_emergency(text: str) -> bool:
    # 词表快速命中（第一道），语义级用 LLM 复核（第二道）
    return any(w in text for w in EMERGENCY_WORDS)


def detect_violation(text: str) -> bool:
    # 索要诊断/开药/治疗 -> 拒答
    return any(w in text for w in VIOLATION_WORDS)


def detect_emotion(text: str) -> str | None:
    for w, tag in EMOTION_WORDS.items():
        if w in text:
            return tag
    return None
```

---

## 6. 主 Agent（AgentBase 子类）——一次 reply 编排全流程

```python
class PreConsultAgent(AgentBase):
    """预问诊医助：追问->槽位填充->完成度->报告生成->科室推荐"""
    def __init__(self, model, formatter, dept_mapper, template_bank):
        super().__init__(model=model, formatter=formatter,
                         name="pre_consult", sys_prompt=SYSTEM_PROMPT)
        self.memory = PreConsultMemory()
        self.state = State.INIT
        self.dept_mapper = dept_mapper      # 症状->科室映射（见《08_症状科室映射表》）
        self.template_bank = template_bank  # 追问/安抚/急重症/免责话术库

    async def reply(self, msg: Msg) -> Msg:
        user_text = msg.content

        # --- ① 急重症（P0）---
        if detect_emergency(user_text):
            self.state = State.EMERGENCY
            reply_text = self.template_bank.emergency()
            self.memory.add_msg(Msg("pre_consult", reply_text, "assistant"))
            return Msg("pre_consult", reply_text, "assistant")

        # --- ② 越界拒答（P0）---
        if detect_violation(user_text):
            self.state = State.REJECTED
            reply_text = self.template_bank.disclaimer()
            self.memory.add_msg(Msg("pre_consult", reply_text, "assistant"))
            return Msg("pre_consult", reply_text, "assistant")

        # --- ③ 情绪安抚（P1）---
        emotion = detect_emotion(user_text)
        comfort = self.template_bank.comfort(emotion) if emotion else ""

        # --- ④ 指代消解 ---
        _, coref_upd = resolve_coreference(user_text, self.memory)

        # --- ⑤ 槽位填充（LLM函数调用） ---
        slot_upd = await extract_slots(self.model, self.memory, user_text)
        self.memory.add_msg(Msg(msg.name or "patient", user_text, "user"))
        self.memory.merge_slots(coref_upd)
        self.memory.merge_slots(slot_upd)

        # --- ⑥ 完成度判断 + 状态路由 ---
        nxt = route(self)
        if nxt == State.REPORT_READY:
            report = await self.generate_report()
            depts = self.dept_mapper.top3(self.memory.slots)
            self.state = State.FINISHED
            reply_text = self.template_bank.report_prefix(report, depts)
        else:
            missing = CompletenessJudge().next_missing(self.memory)
            follow = self.template_bank.ask(missing)   # 轮换不重复
            reply_text = comfort + follow
        self.memory.add_msg(Msg("pre_consult", reply_text, "assistant"))
        return Msg("pre_consult", reply_text, "assistant")

    async def generate_report(self) -> str:
        """由齐备槽位生成结构化报告（模板见《10_提示词与报告模板》）"""
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content":
                        f"请依据以下槽位生成预问诊报告：\n{self.memory.slots}"}]
        resp = await self.model(messages)
        return resp.text
```

---

## 7. AgentScope 流水线串联（sequential_pipeline 示意）

```python
from agentscope.pipeline import sequential_pipeline

# step1: 主诉确认/初始化
def step_init(ctx):
    if not ctx.memory.slots["main_symptom"]:
        return Msg("pre_consult", ctx.template_bank.ask("main_symptom"), "assistant")
    return None

# step2->5: 追问/槽位/完成度/报告 —— 由 PreConsultAgent.reply 内部完成
def step_report(ctx):
    ctx.agent.state = State.FINISHED
    return ctx.agent.reply_last_or_report()

def demo_pipeline(agent):
    msgs = [Msg("system", SYSTEM_PROMPT, "system")]
    user = Msg("patient", "我胸口疼三天了", "user")
    return sequential_pipeline([agent], user_msg=user)   # 逐轮驱动 Agent
```

> pipeline 即"顺序执行、上一步输出作为下一步输入"的流式驱动；本系统把主逻辑集中在 `PreConsultAgent.reply`（§6），pipeline 层保持薄壳便于替换策略。

---

## 8. 依赖目录建议

```text
backend/app/agent/
  __init__.py
  prompts.py            # SYSTEM_PROMPT + 报告模板（见文档10）
  slots.py              # SLOT_KEYS / PreConsultMemory / SlotManager
  coreference.py        # §3 指代消解
  judgers.py            # CompletenessJudge / detect_emergency/emotion/violation
  templates.py          # TemplateBank（见文档11）
  pre_consult_agent.py  # §6 PreConsultAgent
  dept_mapper.py        # 调用症状-科室映射
```