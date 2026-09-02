"""
字源库服务（周易 / 本草纲目 / 神农本草经 / 山海经）

镜像 PoetryDatabase 接口，供引擎层「统一出处抽象」消费。
额外提供「姓+名 连续 n-gram 索引」，供韵味评分 S1 成词成典 O(1) 查询。
"""

import json
from pathlib import Path
from typing import Optional
from app.core.config import settings


def _is_cjk(ch: str) -> bool:
    """判断是否为 CJK 基本区汉字。"""
    return "\u4e00" <= ch <= "\u9fff"


def extract_cjk_ngrams(text: str, min_len: int = 2, max_len: int = 3) -> list[str]:
    """从文本中抽取 2~3 字 CJK 连续子串（含书名号/标点打断后仍保留连词）。

    用于「姓+名」成词成典索引：姓+名 通常是 2~3 字，故只需 2/3 字 n-gram。
    """
    if not text:
        return []
    grams: list[str] = []
    # 先提取连续 CJK 片段
    buf: list[str] = []
    for ch in text:
        if _is_cjk(ch):
            buf.append(ch)
        else:
            if buf:
                grams.extend(_grams_from_run(buf, min_len, max_len))
                buf = []
    if buf:
        grams.extend(_grams_from_run(buf, min_len, max_len))
    return grams


def _grams_from_run(run: list[str], min_len: int, max_len: int) -> list[str]:
    """对一段连续 CJK 字序列抽取 n-gram。"""
    out: list[str] = []
    for n in range(min_len, max_len + 1):
        for i in range(0, len(run) - n + 1):
            out.append("".join(run[i:i + n]))
    return out


class SourceDatabase:
    """字源条目库"""

    _instance = None
    _entries = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        path = settings.SOURCE_DIR / settings.SOURCE_ENTRIES_FILE
        if not path.exists():
            self._entries = []
            self._fullname_index: dict[str, dict] = {}
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._entries = [self.normalize(e) for e in data.get("entries", [])]
        self._build_fullname_index()

    def _build_fullname_index(self):
        """预构建「姓+名 连词索引」：对 text/original_text/title/citation 抽 2~3 字 CJK n-gram。"""
        self._fullname_index: dict[str, dict] = {}
        for entry in self._entries:
            for field in ("text", "original_text", "title", "citation"):
                text = entry.get(field) or ""
                for gram in extract_cjk_ngrams(text, 2, 3):
                    # 保留首个命中条目即可（同词多出处的歧义不影响 S1 判定）
                    self._fullname_index.setdefault(gram, entry)

    @staticmethod
    def normalize(entry: dict) -> dict:
        """读层兜底：对缺失字段补默认值，保证新旧数据混用不抛 KeyError。"""
        return {
            "id": entry.get("id", ""),
            "source": entry.get("source", ""),
            "source_class": entry.get("source_class", "经史子集"),
            "category": entry.get("category", "典籍章句"),
            "title": entry.get("title", ""),
            "author": entry.get("author", "佚名"),
            "dynasty": entry.get("dynasty", ""),
            "text": entry.get("text", ""),
            "original_text": entry.get("original_text"),
            "citation": entry.get("citation", ""),
            "recommend_chars": entry.get("recommend_chars", []),
            "emotion": entry.get("emotion", "中性"),
            "imagery": entry.get("imagery", []),
            "gender": entry.get("gender", "中"),
            "scene": entry.get("scene", ""),
            "tags": entry.get("tags", []),
            "provenance": entry.get("provenance", ""),
        }

    @staticmethod
    def _exclude_sad(entries: list[dict], include_sad: bool) -> list[dict]:
        if include_sad:
            return entries
        return [e for e in entries if e.get("emotion", "中性") != "哀伤"]

    def get_by_char(self, char: str, include_sad: bool = False) -> list[dict]:
        """按推荐用字查找（默认排除哀伤）。"""
        return self._exclude_sad(
            [e for e in self._entries if char in e["recommend_chars"]],
            include_sad,
        )

    def get_by_imagery(self, imagery: str, include_sad: bool = False) -> list[dict]:
        return self._exclude_sad(
            [e for e in self._entries if imagery in e["imagery"]],
            include_sad,
        )

    def get_by_source(self, source: str, include_sad: bool = False) -> list[dict]:
        return self._exclude_sad(
            [e for e in self._entries if e["source"] == source],
            include_sad,
        )

    def get_by_gender(self, gender: str, include_sad: bool = False) -> list[dict]:
        g = {"male": "男", "female": "女"}.get(gender, gender)
        if g == "中":
            return self._exclude_sad(self._entries, include_sad)
        return self._exclude_sad(
            [e for e in self._entries if e["gender"] in (g, "中")],
            include_sad,
        )

    def get_by_fullname_ngram(self, surname: str, given_name: str) -> Optional[dict]:
        """按「姓+名」连续子串查找条目（供 S1 成词成典），未命中返回 None。"""
        full = surname + given_name
        return self._fullname_index.get(full)

    def filter(
        self,
        char: str = None,
        imagery: str = None,
        source: str = None,
        gender: str = None,
        include_sad: bool = False,
    ) -> list[dict]:
        result = self._exclude_sad(self._entries, include_sad)
        if char:
            result = [e for e in result if char in e["recommend_chars"]]
        if imagery:
            result = [e for e in result if imagery in e["imagery"]]
        if source:
            result = [e for e in result if e["source"] == source]
        if gender and gender != "中":
            g = {"male": "男", "female": "女"}.get(gender, gender)
            result = [e for e in result if e["gender"] in (g, "中")]
        return result

    def get_all(self, include_sad: bool = False) -> list[dict]:
        return self._exclude_sad(self._entries, include_sad)

    @property
    def total(self) -> int:
        return len(self._entries)
