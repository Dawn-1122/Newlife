"""
诗词典故库服务
"""

import json
from pathlib import Path
from typing import Optional
from app.core.config import settings


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
        self._poems = data["poems"]

    def get_by_char(self, char: str) -> list[dict]:
        """按推荐用字查找诗词"""
        return [p for p in self._poems if char in p["recommend_chars"]]

    def get_by_imagery(self, imagery: str) -> list[dict]:
        """按意象查找"""
        return [p for p in self._poems if imagery in p["imagery"]]

    def get_by_source(self, source: str) -> list[dict]:
        """按来源查找（诗经/楚辞/唐诗/宋词）"""
        return [p for p in self._poems if p["source"] == source]

    def get_by_gender(self, gender: str) -> list[dict]:
        """按适合性别查找"""
        if gender == "中":
            return self._poems
        return [
            p for p in self._poems
            if p["gender"] in (gender, "中")
        ]

    def filter(
        self,
        char: str = None,
        imagery: str = None,
        source: str = None,
        gender: str = None,
    ) -> list[dict]:
        """多条件筛选"""
        result = self._poems
        if char:
            result = [p for p in result if char in p["recommend_chars"]]
        if imagery:
            result = [p for p in result if imagery in p["imagery"]]
        if source:
            result = [p for p in result if p["source"] == source]
        if gender and gender != "中":
            result = [p for p in result if p["gender"] in (gender, "中")]
        return result

    def get_all(self) -> list[dict]:
        return self._poems

    @property
    def total(self) -> int:
        return len(self._poems)
