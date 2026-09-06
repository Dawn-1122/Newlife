"""
韵味评分器（核心）

五维韵味评分（满分 100）：
    YunWei = P出处(0-35) + I意象(0-25) + L余味(0-15) + C名内呼应(0-10) + S姓氏协调(0-15)

设计原则：
1. 只用量化可得的信号，不人工主观打分，不用 LLM 参与排序。
2. 生僻度/常用度/笔画数绝不进入韵味公式。
3. 评估「姓+名」整体：姓的字义/意象由姓氏字典提供（S 维度），名内呼应 C 只评「名」。
4. 逐维度兜底，任何名字都能算出分数、可排序。
"""

import re
from typing import Optional
from app.core.constants import RADICAL_IMAGERY_FAMILIES, FAMOUS_PHRASES, VERB_CHARS
from app.core.naming_options import (
    PROVENANCE_SAME_SOURCE,
    PROVENANCE_SINGLE_CHAR,
    PROVENANCE_FAMOUS_PENALTY,
    IMAGERY_BASE,
    IMAGERY_PER_HIT,
    IMAGERY_MAX,
    AFTERTASTE_PER_SENSE,
    AFTERTASTE_MAX,
    S1_MAX,
    S2_MAX,
    MEANING_OPTIONS,
    STYLE_OPTIONS,
)
from app.services.poetry_database import PoetryDatabase
from app.services.source_database import SourceDatabase
from app.services.surname_database import SurnameDatabase
from app.services.surname_fit import SurnameFit


class YunWeiScorer:
    """五维韵味评分器"""

    # 义项切分分隔符（按设计：、 ， , ; ；）
    _SENSE_SEP = re.compile(r"[、，,;；]")

    # 内置意象关键词（无出处条目时回退文本匹配用）
    _BUILTIN_IMAGERY_KEYWORDS = [
        "智慧", "聪明", "博学", "睿智", "才思", "聪慧",
        "健康", "长寿", "康健", "安康", "松柏", "强健",
        "勇敢", "坚毅", "刚强", "无畏", "勇毅", "果敢",
        "温婉", "温柔", "娴静", "淑雅", "婉约", "柔美",
        "富贵", "富足", "荣华", "昌盛", "丰裕", "兴旺",
        "平安", "安宁", "祥和", "顺遂", "宁静", "安稳",
        "才华", "文采", "才情", "聪颖", "才俊", "卓越",
        "品德", "德行", "仁德", "贤良", "高洁", "正直",
        "风雅", "古典", "清雅", "雅正", "怀古",
        "灵动", "清新", "山水", "花木", "晨露",
        "宏大", "沉稳", "家国", "志向", "山川",
    ]

    def __init__(
        self,
        surname_db: Optional[SurnameDatabase] = None,
        source_db: Optional[SourceDatabase] = None,
        poetry_db: Optional[PoetryDatabase] = None,
    ):
        self.surname_db = surname_db or SurnameDatabase()
        self.source_db = source_db or SourceDatabase()
        self.poetry_db = poetry_db or PoetryDatabase()
        self.surname_fit = SurnameFit()

    # ── 主入口 ──

    def score(
        self,
        surname: str,
        chars_info: list[dict],
        entry: Optional[dict] = None,
    ) -> dict:
        """
        计算一个名字的韵味分。

        Args:
            surname: 姓氏（单姓或复姓）
            chars_info: 「名」各字信息列表（不含姓），元素含 char/meaning/detail/shuowen/radical 等
            entry: 匹配到的出处条目（诗词/字源统一 dict），可为 None

        Returns:
            {"total": int, "provenance": int, "imagery": int, "aftertaste": int,
             "coherence": int, "surname_coherence": {"s1": int, "s2": int, "total": int}}
        """
        given_name = "".join(c["char"] for c in chars_info)

        p = self._provenance_score(chars_info, entry)
        i = self._imagery_score(chars_info, entry)
        l = self._aftertaste_score(chars_info)
        c = self._coherence_score(chars_info)
        s1, s2 = self._surname_coherence_score(surname, given_name, chars_info, entry)

        total = p + i + l + c + s1 + s2
        return {
            "total": total,
            "provenance": p,
            "imagery": i,
            "aftertaste": l,
            "coherence": c,
            "surname_coherence": {"s1": s1, "s2": s2, "total": s1 + s2},
        }

    # ── P 出处分（0~35，只评「名」） ──

    def _provenance_score(self, chars_info: list[dict], entry: Optional[dict]) -> int:
        name_chars = [c["char"] for c in chars_info]
        if not name_chars:
            return 0
        # 同源：名所有字 ∈ 同一条出处的 recommend_chars
        if entry:
            rec = entry.get("recommend_chars", [])
            if all(ch in rec for ch in name_chars):
                # 冷门句 > 名句直取（避烂大街：名句直取显俗，扣稀缺度）
                if self._is_famous_entry(entry):
                    return PROVENANCE_SAME_SOURCE - PROVENANCE_FAMOUS_PENALTY
                return PROVENANCE_SAME_SOURCE
        # 单字有出处：名至少一个字命中任意出处条目 recommend_chars
        for ch in name_chars:
            if self.poetry_db.get_by_char(ch) or self.source_db.get_by_char(ch):
                return PROVENANCE_SINGLE_CHAR
        return 0

    @staticmethod
    def _is_famous_entry(entry: Optional[dict]) -> bool:
        """判断出处是否命中烂大街名句（名句直取显俗，稀缺度低）。"""
        if not entry:
            return False
        text = " ".join([
            entry.get("text", "") or "",
            entry.get("citation", "") or "",
            entry.get("title", "") or "",
        ])
        return any(phrase in text for phrase in FAMOUS_PHRASES)

    # ── I 意象分（0~25，只评「名」） ──

    def _imagery_score(self, chars_info: list[dict], entry: Optional[dict]) -> int:
        name_text = self._char_text(chars_info)
        tags: list[str] = []
        if entry:
            for tag in (entry.get("imagery", []) or []):
                if tag:
                    tags.append(tag)
            scene = entry.get("scene", "") or ""
            tags.extend(self._scene_keywords(scene))

        k = 0
        if tags:
            for tag in set(tags):
                if tag and tag in name_text:
                    k += 1
        else:
            # 无出处条目（随机组合）：回退匹配内置意象关键词
            k = self._builtin_imagery_hits(name_text)

        return min(IMAGERY_MAX, IMAGERY_BASE + IMAGERY_PER_HIT * k)

    @staticmethod
    def _char_text(chars_info: list[dict]) -> str:
        """拼接名各字的 meaning/detail/shuowen 文本（供意象/余味匹配）。"""
        parts: list[str] = []
        for c in chars_info:
            for field in ("meaning", "detail", "shuowen"):
                v = c.get(field) or ""
                if v:
                    parts.append(v)
        return " ".join(parts)

    @staticmethod
    def _scene_keywords(scene: str) -> list[str]:
        """把 scene 文本按标点切分为关键词（供意象命中）。"""
        if not scene:
            return []
        return [s for s in re.split(r"[，。；,;、\s]+", scene) if s]

    @classmethod
    def _builtin_imagery_hits(cls, name_text: str) -> int:
        """无出处条目时，统计名文本命中内置意象关键词的去重数。"""
        return sum(1 for kw in cls._BUILTIN_IMAGERY_KEYWORDS if kw in name_text)

    # ── L 余味分（0~15，只评「名」） ──

    def _aftertaste_score(self, chars_info: list[dict]) -> int:
        total_senses = 0
        for c in chars_info:
            meaning = c.get("meaning") or ""
            senses = [s for s in self._SENSE_SEP.split(meaning) if s.strip()]
            total_senses += len(senses)
        return min(AFTERTASTE_MAX, AFTERTASTE_PER_SENSE * total_senses)

    # ── C 名内呼应分（0~10，只评「名」，不含姓） ──

    def _coherence_score(self, chars_info: list[dict]) -> int:
        if len(chars_info) < 2:
            return 0  # 单名无「名内」两字呼应
        radicals = [c.get("radical", "") for c in chars_info]
        # 部首同族（需所有字都有部首）
        if all(radicals):
            families = [self._radical_families(r) for r in radicals]
            common = set.intersection(*families) if families else set()
            if common:
                return 10
        # imagery 标签交集
        imagery_sets = [
            set(c.get("imagery", []) or []) for c in chars_info
        ]
        if all(imagery_sets) and set.intersection(*imagery_sets):
            return 5
        # 动名结构（动态画面感）：恰好一个字是动词、另一个不是（动+名 / 名+动）
        verb_flags = [c["char"] in VERB_CHARS for c in chars_info]
        if sum(verb_flags) == 1:
            return 5
        return 0

    @staticmethod
    def _radical_families(radical: str) -> set:
        """返回部首所属的全部意象族（日/月/星可属多个族）。"""
        families = set()
        for name, radicals in RADICAL_IMAGERY_FAMILIES.items():
            if radical in radicals:
                families.add(name)
        return families

    # ── S 姓氏协调分（0~15，评「姓+名」整体） ──

    def _surname_coherence_score(
        self,
        surname: str,
        given_name: str,
        chars_info: list[dict],
        entry: Optional[dict],
    ) -> tuple[int, int]:
        s1 = self._s1_phrase_score(surname, given_name, chars_info, entry)
        s2 = self._s2_imagery_score(surname, chars_info, entry)
        return s1, s2

    def _s1_phrase_score(
        self,
        surname: str,
        given_name: str,
        chars_info: list[dict],
        entry: Optional[dict],
    ) -> int:
        """S1 成词成典分（0~10）：姓+名 是否构成完整词/意象/典实。"""
        # 浑然一体：姓+名 是某出处 text/original_text/title/citation 的连续子串
        ngram_entry = (
            self.source_db.get_by_fullname_ngram(surname, given_name)
            or self.poetry_db.get_by_fullname_ngram(surname, given_name)
        )
        if ngram_entry:
            return S1_MAX

        # 同源到姓：姓与名所有字同属一个条目的 recommend_chars
        if entry:
            rec = entry.get("recommend_chars", [])
            name_chars = [c["char"] for c in chars_info]
            if name_chars and surname in rec and all(ch in rec for ch in name_chars):
                return 6

        # 优先级4：姓氏谐音借力成词（吴+与伦→无与伦比、韩+秋→寒秋）
        boost, _ = self.surname_fit.surname_homophone_boost(surname, given_name)
        if boost:
            return 8

        # 优先级5：名字本身是经典好词/典故（晨曦、浩然、望舒）
        nb, _ = self.surname_fit.name_phrase_boost(given_name)
        if nb:
            return 6

        return 0

    def _s2_imagery_score(
        self,
        surname: str,
        chars_info: list[dict],
        entry: Optional[dict],
    ) -> int:
        """S2 字义/意象呼应分（0~5）：姓的字义/意象与名的字义/意象是否同频。"""
        surname_info = self.surname_db.get_surname(surname)
        if not surname_info:
            return 0

        surname_tags = [t for t in (surname_info.get("imagery", []) or []) if t]
        surname_meaning = surname_info.get("meaning", "") or ""

        # 名的语义场文本 = 名各字 meaning/detail + 名出处的 imagery/scene
        name_text = self._char_text(chars_info)
        entry_tags: list[str] = []
        if entry:
            entry_tags = [t for t in (entry.get("imagery", []) or []) if t]
            name_text += " " + " ".join(entry_tags)
            name_text += " " + (entry.get("scene", "") or "")

        # 姓 imagery 与 名出处 imagery 标签重叠（含共享内容字，如「草木」↔「香草」共享「草」）
        if self._tags_overlap(surname_tags, entry_tags):
            return S2_MAX
        # 姓 imagery 标签出现在名字义/出处文本中
        for tag in surname_tags:
            if tag and tag in name_text:
                return S2_MAX
        # 姓 meaning 关键词出现在名字义/出处文本中
        for kw in self._SENSE_SEP.split(surname_meaning):
            kw = kw.strip()
            if kw and kw in name_text:
                return S2_MAX
        return 0

    @staticmethod
    def _tags_overlap(a: list[str], b: list[str]) -> bool:
        """两个意象标签列表是否「同频」：含子串关系或共享内容汉字。"""
        for x in a:
            if not x:
                continue
            for y in b:
                if not y:
                    continue
                if x in y or y in x:
                    return True
                # 共享任意内容汉字（CJK isalnum 为 True，标点/空格为 False）
                if any(ch in y for ch in x if ch.isalnum()):
                    return True
        return False

    # ── 复用的关键词匹配工具（供韵味/寓意/风格/姓氏呼应复用） ──

    @staticmethod
    def match_keywords(text: str, keywords: list[str]) -> int:
        """统计文本命中关键词列表的次数（去重按关键词计数）。"""
        if not text or not keywords:
            return 0
        return sum(1 for kw in keywords if kw and kw in text)
