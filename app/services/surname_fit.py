"""
姓氏结合模块（需求4）

在「姓 + 名」组合阶段与门槛层引入姓氏意识，解决「只简单堆砌后两个字」的问题：

1. 谐音歧义检测（安全底线，硬排除）：
   全名拼音（无调）匹配负面谐音词表，如 杜子腾→肚子疼、吴德→无德、杨伟→阳痿。
2. 本义冲突检测（高危硬排除）：
   姓氏本义与名字用字冲突，如 朱(红)+红/丹/彤 语义重复、白+云 易生贬义。
3. 三连同调预检（组合优化）：
   姓 + 双字名 若全平或全仄，组合阶段提前跳过（与音律门槛 is_cacophonous 一致）。

所有词表/规则集中在 data/dict/surname_taboo.json，可人工扩充，不改代码。
"""

import json
from pathlib import Path
from typing import Optional
from pypinyin import lazy_pinyin

from app.core.config import settings


class SurnameFit:
    """姓氏结合评估器"""

    _instance = None
    _homophone_taboo: dict[str, str] = {}
    _meaning_conflict: dict[str, list[str]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        path = settings.DICT_DIR / settings.SURNAME_TABOO_FILE
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._homophone_taboo = {
            k: v for k, v in (data.get("homophone_taboo") or {}).items() if k
        }
        self._meaning_conflict = {
            k: list(v) for k, v in (data.get("meaning_conflict") or {}).items()
        }

        # 谐音借力词表（正向，优先级4/5）
        boost_path = settings.DICT_DIR / settings.HOMOPHONE_BOOST_FILE
        if boost_path.exists():
            with open(boost_path, "r", encoding="utf-8") as bf:
                boost = json.load(bf)
            self._surname_homophone = {
                k: v for k, v in (boost.get("surname_homophone") or {}).items()
                if k and v
            }
            self._positive_phrases = [
                p for p in (boost.get("positive_phrases") or []) if p
            ]
            self._name_phrases = [
                p for p in (boost.get("name_phrases") or []) if p
            ]

    # ── 谐音歧义 ──

    @staticmethod
    def _plain_pinyin(text: str) -> str:
        """全名拼音（无调、无空格）。"""
        return "".join(lazy_pinyin(text))

    def is_homophone_taboo(self, surname: str, given_name: str) -> tuple[bool, str]:
        """
        谐音歧义检测。

        全名拼音与负面词表「完整匹配」或「前缀匹配」（词长>=4，即至少两字）即命中。
        - 完整匹配：吴德 → wude == 无德
        - 前缀匹配：吴德凯 → wudekai 以 wude 开头（谐音「无德凯」）

        Returns:
            (是否命中, 命中的负面词或空串)
        """
        if not self._homophone_taboo:
            return False, ""
        full_pinyin = self._plain_pinyin(surname + given_name)
        for taboo_py, word in self._homophone_taboo.items():
            if len(taboo_py) < 4:
                continue  # 单字负面词误伤高，不启用
            if full_pinyin == taboo_py or full_pinyin.startswith(taboo_py):
                return True, word
        return False, ""

    # ── 本义冲突 ──

    def is_meaning_conflict(self, surname: str, given_name: str) -> tuple[bool, str]:
        """
        姓氏本义冲突检测：名字用字命中该姓的禁配字 → 硬排除。

        Returns:
            (是否冲突, 冲突说明)
        """
        conflict_chars = self._meaning_conflict.get(surname)
        if not conflict_chars:
            return False, ""
        for ch in given_name:
            if ch in conflict_chars:
                return True, f"姓氏「{surname}」与「{ch}」本义冲突"
        return False, ""

    # ── 三连同调预检 ──

    @staticmethod
    def tri_tone_conflict(surname: str, name_chars: list[str]) -> bool:
        """
        姓 + 双字名 是否三连同调（全平或全仄）。

        与 PhoneticsScorer.is_cacophonous 的「平平平/仄仄仄」一致，
        用于组合阶段提前跳过，减少无效组合。
        单字名（姓+名共2字）不因平仄同调排除，返回 False。
        """
        if len(name_chars) != 2:
            return False
        from app.services.phonetics import PhoneticsScorer
        tones = []
        for ch in [surname] + list(name_chars):
            _, tone = PhoneticsScorer.get_pinyin(ch)
            if tone == 0:
                return False  # 轻声/无法识读，不判定
            tones.append(tone)
        # 平 = 1/2 声，仄 = 3/4 声
        types = {1: "平", 2: "平", 3: "仄", 4: "仄"}
        t = [types[x] for x in tones]
        return len(set(t)) == 1

    # ── 谐音借力（正向，优先级4/5） ──

    def surname_homophone_boost(self, surname: str, given_name: str) -> tuple[bool, str]:
        """
        优先级4：姓氏谐音借力成词。

        姓的谐音字 + 名 = 褒义词/成语（吴+与伦→无与伦比、韩+秋→寒秋、段+章→断章取义）。
        返回 (是否命中, 命中的褒义词)。
        """
        homophone = self._surname_homophone.get(surname)
        if not homophone:
            return False, ""
        full_py = self._plain_pinyin(homophone + given_name)
        if len(full_py) < 4:
            return False, ""
        for phrase in self._positive_phrases:
            if self._plain_pinyin(phrase).startswith(full_py):
                return True, phrase
        return False, ""

    def name_phrase_boost(self, given_name: str) -> tuple[bool, str]:
        """
        优先级5：名字本身是经典好词/典故（晨曦、浩然、望舒、扶苏等）。

        这类名字自带文化余味与辨识度，属「惊艳」名字的重要来源。
        """
        if len(given_name) < 2:
            return False, ""
        for phrase in self._name_phrases:
            if given_name == phrase:
                return True, phrase
        return False, ""
