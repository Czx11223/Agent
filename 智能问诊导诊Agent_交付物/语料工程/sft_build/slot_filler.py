# -*- coding: utf-8 -*-
"""槽位抽取器：从患者文本抽取 6 类槽位（main_symptom/body_part/duration/
accompanying_symptom/past_history/allergy_history）。

词表来源：
- main_symptom：symptom_lexicon_full.csv 的判定词
- duration：复用 config.DURATION_RE
- body_part/accompanying_symptom/past_history/allergy_history：config 扩展关键词表
"""
import csv
import re
from typing import List, Tuple

from config import (
    LEXICON_CSV, SLOT_KEYS, DURATION_RE, BODY_PART_WORDS,
    ACCOMPANYING_WORDS, PAST_HISTORY_WORDS, ALLERGY_WORDS,
    RULE_QUESTIONS,
)


def _load_lexicon_terms(path: str = LEXICON_CSV) -> List[Tuple[str, str]]:
    """从 symptom_lexicon_full.csv 加载 (判定词, canon) 对。"""
    pairs: List[Tuple[str, str]] = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            terms = (row.get("判定词") or "").split("、")
            canon = row.get("symptom_key") or ""
            for t in terms:
                t = t.strip()
                if t and canon:
                    pairs.append((t, canon))
    # 按词长度降序排列，优先匹配更具体的判定词（如"偏头痛"优先于"头痛"）
    pairs.sort(key=lambda x: -len(x[0]))
    return pairs


# 模块级缓存（只加载一次）
_LEXICON_PAIRS: List[Tuple[str, str]] | None = None


def lexicon_pairs() -> List[Tuple[str, str]]:
    global _LEXICON_PAIRS
    if _LEXICON_PAIRS is None:
        _LEXICON_PAIRS = _load_lexicon_terms()
    return _LEXICON_PAIRS


def _find_first(text: str, words: list[str]) -> str:
    """返回首个命中 text 的关键词本身（用于槽位回填）。"""
    for w in words:
        if w in text:
            return w
    return ""


def extract_slots(text: str) -> dict:
    """从患者文本抽取 6 类槽位，返回 {key: value}（未命中为空字符串）。"""
    text = text or ""
    slots = {k: "" for k in SLOT_KEYS}

    # 1) main_symptom：用词表命中第一个（最长匹配优先）
    for term, canon in lexicon_pairs():
        if term in text:
            slots["main_symptom"] = canon
            break

    # 2) duration：正则匹配
    m = DURATION_RE.search(text)
    if m:
        slots["duration"] = m.group(0)

    # 3) body_part
    bp = _find_first(text, sorted(BODY_PART_WORDS, key=len, reverse=True))
    if bp:
        slots["body_part"] = bp

    # 4) accompanying_symptom
    ac = _find_first(text, sorted(ACCOMPANYING_WORDS, key=len, reverse=True))
    if ac:
        slots["accompanying_symptom"] = ac

    # 5) past_history
    ph = _find_first(text, sorted(PAST_HISTORY_WORDS, key=len, reverse=True))
    if ph:
        slots["past_history"] = ph

    # 6) allergy_history
    al = _find_first(text, sorted(ALLERGY_WORDS, key=len, reverse=True))
    if al:
        slots["allergy_history"] = al

    return slots


def filled_count(slots: dict) -> int:
    """统计非空槽位数。"""
    return sum(1 for v in slots.values() if v)


def next_missing_slot(slots: dict) -> str:
    """返回下一个应追问的槽位 key（按 SLOT_KEYS 顺序，main_symptom 满后开始问 body_part）。
    若全部已填，返回空字符串。"""
    for k in SLOT_KEYS:
        if not slots.get(k):
            return k
    return ""


def pick_next_question(slots: dict) -> str:
    """根据下一个缺失槽位，从 RULE_QUESTIONS 选模板；若 main_symptom 缺失则反问主诉。"""
    missing = next_missing_slot(slots)
    if missing == "main_symptom":
        return "请问您目前最主要的不适是什么？可以描述一下您的症状。"
    for key, q in RULE_QUESTIONS:
        if key == missing:
            return q
    return "请问还有其他需要补充的吗？"
