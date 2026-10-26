"""预问诊导诊 Agent 编排核心（基于 AgentScope 消息模型）。

编排：本地急重症/词汇预检 + LLM JSON 决策 + 槽位合并 + 报告/科室规则生成。
多轮对话状态（消息记忆 + 槽位）统一采用 AgentScope 的 Msg 消息模型管理，
对话策略编排（追问→槽位填充→完成度判断→报告生成→科室推荐）沿用原有逻辑。

人设：预问诊医助，严禁诊断，不开药。追问链：主诉→部位→时间→伴随→既往→过敏。
"""
import json
import re

from agentscope.message import Msg, TextBlock

from ..core import config
from ..core.errors import ApiError
from ..llm.client import chat_json
from . import dept_map

SLOT_KEYS = [
    "main_symptom", "body_part", "duration",
    "accompanying_symptom", "past_history", "allergy_history",
]

# 本地规则降级用
DURATION_RE = re.compile(
    r"(\d+\s*[个小时天周月年]|[一二两三四五六七八九十\d]+个?[天周月年]|半[年月]|数天|很少久|很久|刚刚|昨天|前天|好几天|一段时间)"
)
SOOTHE_RE = re.compile(r"疼|痛|难受|不舒服|焦虑|紧张|害怕|太难受")
# 指代消解：地点指示代词（如"也是这里疼""那里也不舒服"）
DEIXIS_RE = re.compile(r"(这里|这儿|那里|那儿|这边|那边|这个地方|那个地方|该处|此处)")
# 患者"无更多症状/不清楚"类否定回答：不作为槽位内容，避免污染报告
NO_MORE_RE = re.compile(r"没有(其他|别的)?(不舒服|症状|不适)?|暂时没有|无其他|没别的|不清楚|不知道|说不上")

_RULE_QUESTIONS = [
    ("body_part", "请问不适主要集中在哪个部位？"),
    ("duration", "这个情况大概持续多久了？（比如一两天、两周或更久）"),
    ("accompanying_symptom", "还有没有伴随的其他症状？如发热、恶心、头晕等。"),
    ("past_history", "您既往有没有相关病史？如高血压、糖尿病、哮喘等。"),
    ("allergy_history", "您有没有药物或食物过敏史？"),
]

# 本地确定性兜底抽取时，非"时间/部位"类回答的落位顺序
_ABSORB_ORDER = ("body_part", "accompanying_symptom", "past_history", "allergy_history")

SYSTEM_PROMPT = """你是医疗机构的【预问诊导诊助手】。约束：
1. 严禁做医学诊断，不开药，不做治疗方案；你的任务只是收集症状信息并指引就诊科室。
2. 患者出现急重症（剧烈胸痛、呼吸困难、昏迷、大出血等）时，action 必须为 emergency。
3. 用户索要诊断或开药/处方时，action 必须为 rejected，并给出免责说明。
4. 察觉患者焦虑/疼痛情绪，可输出 comfort 安抚语。
5. 追问按优先级：主要症状→部位→持续时间→伴随症状→既往史→过敏史；信息由患者提供。
6. 当六大要素中的五个关键项（主诉、部位、时间、伴随、既往；过敏可选）收集完毕，action 为 report。
7. 每次只输出一个 JSON 对象，不允许出现 JSON 以外的文字。

输出格式（JSON）：
{
  "action": "ask|emergency|rejected|report",
  "comfort": "安抚语(可选，没有则空字符串)",
  "question": "给患者的自然语言回复（追问或报告说明）",
  "slots": {"main_symptom":"", "body_part":"", "duration":"", "accompanying_symptom":"", "past_history":"", "allergy_history":""}
}
slots 中请回填患者已经说明的字段（未知留空字符串）。"""


def _text_block(text: str) -> list[TextBlock]:
    return [TextBlock(type="text", text=text)]


def _build_messages(user_text: str, slots: dict, history: list[dict]) -> list[Msg]:
    """用 AgentScope Msg 构造多轮对话消息序列（系统提示 + 近 6 轮记忆 + 当前输入）。"""
    msgs: list[Msg] = [Msg(name="system", role="system", content=_text_block(SYSTEM_PROMPT))]
    for h in history[-6:]:  # 近 6 轮上下文，控 token
        role = "assistant" if h["role"] == "agent" else h["role"]
        msgs.append(Msg(name=role, role=role, content=_text_block(h["content"])))
    known = {k: (v or "未知") for k, v in slots.items() if v}
    prompt = {
        "当前用户消息": user_text,
        "目前已采集槽位": known,
        "任务": "请按规则继续追问或生成报告",
    }
    msgs.append(Msg(name="user", role="user", content=_text_block(json.dumps(prompt, ensure_ascii=False))))
    return msgs


def _msgs_to_openai(msgs: list[Msg]) -> list[dict]:
    """AgentScope Msg → OpenAI 兼容消息（供 httpx 客户端调用）。"""
    return [{"role": m.role, "content": m.get_text_content()} for m in msgs]


class PreConsultAgent:
    """基于 AgentScope Msg 的多轮对话 Agent：槽位状态 + 消息记忆 + 策略编排。"""

    NAME = "预问诊医助"

    def __init__(self, slots: dict | None = None, history: list[dict] | None = None):
        self.slots = {k: (slots or {}).get(k) or "" for k in SLOT_KEYS}
        self.history = history or []
        self.memory: list[Msg] = []  # AgentScope 消息记忆（多轮对话状态）
        self.last_decision: dict = {}
        self.degraded = False  # 评测用：本轮是否发生 LLM 降级（静默回退到本地规则）

    @staticmethod
    def user_msg(text: str) -> Msg:
        return Msg(name="user", role="user", content=_text_block(text))

    def reply(self, msg: Msg) -> Msg:
        """AgentScope 风格入口：输入用户 Msg，返回助手 Msg，并维护消息记忆。"""
        text = msg.get_text_content()
        decision = self.step(text)
        self.last_decision = decision
        out = Msg(name=self.NAME, role="assistant", content=_text_block(decision["question"]))
        self.memory.extend([msg, out])
        return out

    def _resolve_coreference(self, text: str) -> str:
        """指代消解：把"这里/那里"等地点指代绑定到上文已知部位（如"也是这里疼"）。"""
        if not DEIXIS_RE.search(text):
            return text
        part = self.slots.get("body_part") or self._last_body_part_from_history()
        if not part:
            return text
        return DEIXIS_RE.sub(part, text)

    def _last_body_part_from_history(self) -> str:
        for h in reversed(self.history):
            part = dept_map.find_body_part(h.get("content", ""))
            if part:
                return part
        return ""

    def _absorb_local_slots(self, text: str) -> None:
        """确定性槽位兜底抽取（与本地规则降级同源），仅补全空槽位：
        LLM 漏填槽位时，保证患者已述的关键信息不被丢弃。"""
        text = (text or "").strip()
        if not text or NO_MORE_RE.search(text):
            return
        d = DURATION_RE.search(text)
        if d and not self.slots["duration"]:
            self.slots["duration"] = d.group(0)
        part = dept_map.find_body_part(text)
        if part and not self.slots["body_part"]:
            self.slots["body_part"] = part
        if not self.slots["past_history"]:
            ph = dept_map.find_past_history(text)
            if ph:  # 既往病史：如"癫痫"、"肺结核"，单独归入既往史而非主诉
                self.slots["past_history"] = ph
                return
        if not self.slots["main_symptom"]:
            self.slots["main_symptom"] = text  # 首轮主诉
            return
        if d or part:  # 本条已按 时间/部位 归位，不再重复占用其它槽位
            return
        for k in _ABSORB_ORDER:
            if not self.slots[k]:
                self.slots[k] = text
                return

    def step(self, user_text: str) -> dict:
        # 指代消解：先结合上下文消解"也是这里疼"之类的地点指代
        user_text = self._resolve_coreference(user_text)
        # 安全兜底：本地急诊命中就不必依赖 LLM
        if dept_map.is_emergency(user_text):
            return {
                "action": "emergency",
                "comfort": "请保持冷静",
                "question": EMERGENCY_TEMPLATE,
                "slots": {},
            }

        msgs = _build_messages(user_text, self.slots, self.history)
        try:
            decision = chat_json(_msgs_to_openai(msgs))
        except ApiError as e:
            if e.code in (5001, 5002):  # LLM 未配置 / 调用失败
                # 回退本地规则继续对话，避免未配置 LLM 时静默无响应
                self.degraded = True
                import sys
                print(f"[agent] LLM 降级，原因-> {e}", file=sys.stderr)
                return self._rule_step(user_text)
            raise

        action = decision.get("action", "ask")
        slots_delta = decision.get("slots") or {}
        for k in SLOT_KEYS:
            v = slots_delta.get(k)
            if v and not self.slots.get(k):
                self.slots[k] = str(v).strip()
        # 确定性兜底：LLM 漏填时用本地规则补全患者已述信息，避免追问覆盖率塌陷
        self._absorb_local_slots(user_text)

        question = (decision.get("question") or "").strip() or "请问还有其他症状吗？"
        # report 前后置校验：关键报告字段不得为空，否则退回追问
        if action == "report" and not self._report_fields_ready():
            action = "ask"
            question = "为了给您生成完整报告，还需要确认一下：您是否还有其他伴随症状或既往病史？（如已提供请忽略）"

        return {
            "action": action,
            "comfort": (decision.get("comfort") or "").strip(),
            "question": question,
            "slots": {k: v for k, v in self.slots.items()},
        }

    def _report_fields_ready(self) -> bool:
        return bool(self.slots["main_symptom"]) and bool(self.slots["duration"])
        # 主诉 + 时间齐即可出报告，其余字段可缺省并回填"未提供"（兼顾残缺输入场景）

    def _rule_step(self, user_text: str) -> dict:
        """LLM 不可用（未配置 key / 调用失败）时的本地规则降级：
        仅收集信息并逐项追问，不开药、不诊断，收集足够即生成报告与科室推荐。"""
        soothe = "听到您的不适，先别着急，我们一步一步来。 " if SOOTHE_RE.search(user_text) else ""

        filled_duration = False
        d = DURATION_RE.search(user_text)
        if d and not self.slots["duration"]:
            self.slots["duration"] = d.group(0)
            filled_duration = True

        if not self.slots["main_symptom"]:
            self.slots["main_symptom"] = user_text
            for key, q in _RULE_QUESTIONS:
                if not self.slots[key]:
                    return {"action": "ask", "comfort": "", "question": soothe + q, "slots": dict(self.slots)}
            return self._report()

        # 后续轮：若本条未被时长正则消费，则吸收到当前缺失项
        if not filled_duration:
            for key, _ in _RULE_QUESTIONS:
                if not self.slots[key]:
                    self.slots[key] = user_text
                    break

        for key, q in _RULE_QUESTIONS:
            if not self.slots[key]:
                return {"action": "ask", "comfort": "", "question": soothe + q, "slots": dict(self.slots)}
        return self._report()

    def _report(self) -> dict:
        return {
            "action": "report",
            "comfort": "",
            "question": "好的，已收集到足够信息，我这就为您生成预问诊报告并推荐就诊科室。",
            "slots": dict(self.slots),
        }

    def build_report(self) -> dict:
        s = self.slots
        chief = "、".join(x for x in [s["main_symptom"], s["body_part"]] if x) or "主诉待确认"
        present = f"{s.get('main_symptom') or '未明确'} 已持续 {s.get('duration') or '时间未明确'}"
        if s.get("accompanying_symptom"):
            present += f"，伴 {s['accompanying_symptom']}"
        allergy = s.get("allergy_history") or "无已知药物/食物过敏"
        past = s.get("past_history") or "未提供"
        depts = dept_map.recommend_top3(" ".join(x for x in s.values() if x))
        return {
            "chief_complaint": chief,
            "present_illness": present,
            "allergy_history": allergy,
            "past_history": past,
            "recommend_dept_top3": json.dumps(depts, ensure_ascii=False),
            "disclaimer": dept_map.DISCLAIMER,
        }


EMERGENCY_TEMPLATE = (
    "您描述的症状属于需要紧急处置的情况，请立即停止在线问诊。"
    "建议您现在就前往最近的急诊科，或拨打120急救电话求助；在等待期间请尽量保持体位稳定、有人陪同。切勿驾车前往。"
    "（本提示仅供安全提示，不做诊断。）"
)