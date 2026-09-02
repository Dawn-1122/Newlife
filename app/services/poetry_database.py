"""
诗词典故库服务
"""

import json
from pathlib import Path
from typing import Optional
from app.core.config import settings
from app.services.source_database import extract_cjk_ngrams


class PoetryDatabase:
    """诗词典故库"""

    _instance = None
    _poems = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        path = settings.POETRY_DIR / settings.POETRY_DB_FILE
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._poems = [self.normalize(p) for p in data["poems"]]
        self._build_fullname_index()

    def _build_fullname_index(self):
        """预构建「姓+名 连词索引」：对 text/original_text/title/citation 抽 2~3 字 CJK n-gram。"""
        self._fullname_index: dict[str, dict] = {}
        for poem in self._poems:
            for field in ("text", "original_text", "title", "citation"):
                text = poem.get(field) or ""
                for gram in extract_cjk_ngrams(text, 2, 3):
                    self._fullname_index.setdefault(gram, poem)

    @staticmethod
    def normalize(poem: dict) -> dict:
        """读层兜底：对缺失字段补默认值，保证旧/新数据混用不抛 KeyError。"""
        return {
            "id": poem.get("id", ""),
            "source": poem.get("source", ""),
            # 现有诗词按 source 直接作为 source_class（6 大类即其大类）
            "source_class": poem.get("source_class", poem.get("source", "")),
            "title": poem.get("title", ""),
            "author": poem.get("author", "佚名"),
            "dynasty": poem.get("dynasty", ""),
            "text": poem.get("text", ""),
            "original_text": poem.get("original_text"),
            "citation": poem.get("citation", ""),
            "recommend_chars": poem.get("recommend_chars", []),
            "emotion": poem.get("emotion", "中性"),
            "imagery": poem.get("imagery", []),
            "gender": poem.get("gender", "中"),
            "scene": poem.get("scene", ""),
            "tags": poem.get("tags", []),
            "provenance": poem.get("provenance", ""),
        }

    def get_by_fullname_ngram(self, surname: str, given_name: str) -> Optional[dict]:
        """按「姓+名」连续子串查找条目（供 S1 成词成典），未命中返回 None。"""
        full = surname + given_name
        return self._fullname_index.get(full)

    @staticmethod
    def _exclude_sad(poems: list[dict], include_sad: bool) -> list[dict]:
        """默认排除哀伤条目（不进起名候选），include_sad=True 时保留。"""
        if include_sad:
            return poems
        return [p for p in poems if p.get("emotion", "中性") != "哀伤"]

    def get_by_char(self, char: str, include_sad: bool = False) -> list[dict]:
        """按推荐用字查找诗词（默认排除哀伤）"""
        return self._exclude_sad(
            [p for p in self._poems if char in p["recommend_chars"]],
            include_sad,
        )

    def get_by_imagery(self, imagery: str, include_sad: bool = False) -> list[dict]:
        """按意象查找（默认排除哀伤）"""
        return self._exclude_sad(
            [p for p in self._poems if imagery in p["imagery"]],
            include_sad,
        )

    def get_by_source(self, source: str, include_sad: bool = False) -> list[dict]:
        """按来源查找（诗经/楚辞/唐诗/宋词/汉魏古诗/经史子集；默认排除哀伤）"""
        return self._exclude_sad(
            [p for p in self._poems if p["source"] == source],
            include_sad,
        )

    def get_by_gender(self, gender: str, include_sad: bool = False) -> list[dict]:
        """按适合性别查找（兼容 male/female 与 男/女；默认排除哀伤）"""
        g = {"male": "男", "female": "女"}.get(gender, gender)
        if g == "中":
            return self._exclude_sad(self._poems, include_sad)
        return self._exclude_sad(
            [p for p in self._poems if p["gender"] in (g, "中")],
            include_sad,
        )

    def filter(
        self,
        char: str = None,
        imagery: str = None,
        source: str = None,
        gender: str = None,
        include_sad: bool = False,
    ) -> list[dict]:
        """多条件筛选（默认排除哀伤条目）"""
        result = self._exclude_sad(self._poems, include_sad)
        if char:
            result = [p for p in result if char in p["recommend_chars"]]
        if imagery:
            result = [p for p in result if imagery in p["imagery"]]
        if source:
            result = [p for p in result if p["source"] == source]
        if gender and gender != "中":
            g = {"male": "男", "female": "女"}.get(gender, gender)
            result = [p for p in result if p["gender"] in (g, "中")]
        return result

    def get_all(self, include_sad: bool = False) -> list[dict]:
        """获取全部诗词（默认排除哀伤条目）"""
        return self._exclude_sad(self._poems, include_sad)

    @property
    def total(self) -> int:
        return len(self._poems)
