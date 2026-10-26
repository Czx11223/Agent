# -*- coding: utf-8 -*-
"""SFT 数据集构造配置：路径、采样数、System Prompt、槽位键、规则常量。

所有常量与 backend/app/agent/pre_consult_agent.py + dept_map.py + blacklist.py 保持同步，
内联在此处以避免跨包导入（sft_build 是独立脚本，不依赖 backend 包安装）。
"""
import os
import re

# ── 路径配置 ──────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
CORPUS_ROOT = os.path.dirname(BASE)                       # 语料工程/
CLEANED_CSV = os.path.join(CORPUS_ROOT, "cleaned_dialogue.csv")
LEXICON_CSV = os.path.join(BASE, "..", "clean_pipeline", "symptom_lexicon_full.csv")
OUTPUT_DIR = os.path.join(BASE, "output")

# ── 采样目标条数 ─────────────────────────────────────────
N_ASK = 8000
N_REPORT = 3000
N_EMERGENCY = 3000
N_REJECTED = 1000
DEV_RATIO = 0.10                                          # 各任务抽 10% 作 dev
N_EVAL = 120                                              # 评测集扩充目标

# ── 槽位键（与 PreConsultAgent.SLOT_KEYS 一致）────────────
SLOT_KEYS = [
    "main_symptom", "body_part", "duration",
    "accompanying_symptom", "past_history", "allergy_history",
]

# ── System Prompt（与 pre_consult_agent.py L35-51 原文同步）─
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

# ── 追问模板（与 pre_consult_agent.py _RULE_QUESTIONS 一致）─
RULE_QUESTIONS = [
    ("body_part", "请问不适主要集中在哪个部位？"),
    ("duration", "这个情况大概持续多久了？（比如一两天、两周或更久）"),
    ("accompanying_symptom", "还有没有伴随的其他症状？如发热、恶心、头晕等。"),
    ("past_history", "您既往有没有相关病史？如高血压、糖尿病、哮喘等。"),
    ("allergy_history", "您有没有药物或食物过敏史？"),
]

# ── 时长正则（与 pre_consult_agent.py DURATION_RE 一致）──
DURATION_RE = re.compile(
    r"(\d+\s*[个小时天周月年]|[一二两三四五六七八九十\d]+个?[天周月年]|半[年月]|数天|很少久|很久|刚刚|昨天|前天|好几天|一段时间)"
)

# ── 安抚触发正则（与 pre_consult_agent.py SOOTHE_RE 一致）─
SOOTHE_RE = re.compile(r"疼|痛|难受|不舒服|焦虑|紧张|害怕|太难受")

# ── 急诊模板（与 pre_consult_agent.py EMERGENCY_TEMPLATE 一致）─
EMERGENCY_TEMPLATE = (
    "您描述的症状属于需要紧急处置的情况，请立即停止在线问诊。"
    "建议您现在就前往最近的急诊科，或拨打120急救电话求助；在等待期间请尽量保持体位稳定、有人陪同。切勿驾车前往。"
    "（本提示仅供安全提示，不做诊断。）"
)

# ── 科室关键词映射（与 dept_map.py DEPT_KEYWORDS 一致）──
DEPT_KEYWORDS = {
    "呼吸内科": ["咳嗽", "咳痰", "咳血", "气喘", "胸闷", "鼻塞", "流涕", "发热", "喘不上气"],
    "消化内科": ["胃痛", "胃胀", "反酸", "腹痛", "腹泻", "便秘", "恶心", "呕吐", "便血", "烧心", "胃疼"],
    "心血管内科": ["心慌", "心悸", "胸闷", "胸痛", "血压高", "心跳快", "心闷"],
    "神经内科": ["头痛", "头晕", "眩晕", "麻木", "失眠", "偏头痛", "晕厥", "头昏"],
    "骨科": ["关节痛", "腰痛", "膝盖", "颈肩痛", "手麻", "骨折", "腰疼", "关节疼", "腿疼"],
    "皮肤科": ["皮疹", "红疹", "荨麻疹", "瘙痒", "起痘", "脱屑", "皮肤痒", "疙瘩"],
    "内分泌科": ["口渴", "多尿", "消瘦", "乏力", "多饮", "三多"],
    "耳鼻喉科": ["耳鸣", "听力下降", "咽喉痛", "嗓子疼", "耳闷"],
    "妇科": ["月经不调", "痛经", "白带异常", "停经"],
    "儿科": ["小儿咳嗽", "小儿发热", "婴儿腹泻"],
}

# ── 急重症关键词（与 dept_map.py EMERGENCY_KEYWORDS 一致）─
EMERGENCY_KEYWORDS = [
    "胸痛剧烈", "剧烈腹痛", "呼吸困难", "喘不上气", "咯血", "呕血", "大出血",
    "晕倒", "昏迷", "不省人事", "窒息", "休克", "吐了很多血", "便大量血", "心前区压榨",
]

# ── 免责声明（与 dept_map.py DISCLAIMER 一致）────────────
DISCLAIMER = "本预问诊报告仅用于挂号与接诊参考，不构成医学诊断或治疗建议，最终请以执业医师判断为准。"

# ── rejected 任务免责说明 ─────────────────────────────────
REJECTED_TEMPLATE = (
    "很抱歉，作为预问诊助手，我无法提供诊断或开具处方/用药建议。"
    "建议您前往线下医疗机构由执业医师面诊后决定治疗方案。"
    "如果您愿意，可以先描述一下您的症状，我帮您梳理信息并推荐合适的就诊科室。"
)

# ── report 完成提示 ──────────────────────────────────────
REPORT_DONE_QUESTION = "好的，已收集到足够信息，我这就为您生成预问诊报告并推荐就诊科室。"

# ── 扩展槽位关键词表（slot_filler 使用）──────────────────
# 身体部位
BODY_PART_WORDS = [
    "头", "太阳穴", "眼睛", "眼", "耳朵", "耳", "鼻子", "鼻", "嘴", "口腔",
    "嗓子", "喉咙", "咽喉", "脖子", "颈", "肩膀", "肩", "胸", "胸口", "胸部",
    "后背", "背", "腰", "腰部", "肚子", "腹", "腹部", "脐周", "胃", "上腹",
    "下腹", "胳膊", "上肢", "手", "手臂", "手指", "腿", "下肢", "膝盖", "膝",
    "脚", "脚踝", "关节", "皮肤", "脸", "面部", "全身",
]

# 伴随症状
ACCOMPANYING_WORDS = [
    "发热", "发烧", "低烧", "高热", "恶心", "呕吐", "头晕", "头痛",
    "乏力", "没精神", "疲劳", "畏寒", "寒战", "出汗", "盗汗",
    "食欲不振", "消瘦", "失眠", "焦虑", "心慌", "心悸",
    "腹泻", "便秘", "尿频", "尿急", "尿痛",
]

# 既往史
PAST_HISTORY_WORDS = [
    "高血压", "糖尿病", "哮喘", "冠心病", "肝炎", "肾炎", "胃病",
    "过敏", "手术史", "结核", "肿瘤", "癌症", "癫痫", "甲亢", "甲减",
    "乙肝", "肝病", "肾病", "贫血",
]

# 过敏史
ALLERGY_WORDS = [
    "青霉素过敏", "药物过敏", "食物过敏", "海鲜过敏", "花粉过敏",
    "头孢过敏", "磺胺过敏", "阿莫西林过敏", "过敏史",
]


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
