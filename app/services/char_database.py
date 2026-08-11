"""
字库服务

提供汉字查询、按五行筛选、按笔画范围筛选等功能。
"""

import json
from pathlib import Path
from typing import Optional
from app.core.config import settings


class CharDatabase:
    """汉字字库"""

    _instance = None
    _chars = None
    _char_map = None  # 按汉字索引

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """加载数据"""
        path = settings.DICT_DIR / settings.CHAR_DB_FILE
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._chars = data["chars"]
        self._char_map = {}
        for c in self._chars:
            key = c["char"]
            if key not in self._char_map:
                self._char_map[key] = c

    def get_char(self, char: str) -> Optional[dict]:
        """查询单个字"""
        return self._char_map.get(char)

    def get_by_wuxing(self, wuxing: str, gender: str = None) -> list[dict]:
        """按五行筛选"""
        result = [c for c in self._chars if c["wuxing"] == wuxing]
        if gender and gender != "中":
            # 优先匹配性别，但也包含中性
            result = [c for c in result if c["gender"] in (gender, "中")]
        return result

    def get_by_strokes(self, min_strokes: int = 1, max_strokes: int = 30) -> list[dict]:
        """按康熙笔画范围筛选"""
        return [
            c for c in self._chars
            if min_strokes <= c["kangxi_strokes"] <= max_strokes
        ]

    def filter(
        self,
        wuxing: str = None,
        gender: str = None,
        min_strokes: int = None,
        max_strokes: int = None,
        luck: str = None,
    ) -> list[dict]:
        """多条件筛选"""
        result = self._chars
        if wuxing:
            result = [c for c in result if c["wuxing"] == wuxing]
        if gender and gender != "中":
            result = [c for c in result if c["gender"] in (gender, "中")]
        if min_strokes is not None:
            result = [c for c in result if c["kangxi_strokes"] >= min_strokes]
        if max_strokes is not None:
            result = [c for c in result if c["kangxi_strokes"] <= max_strokes]
        if luck:
            result = [c for c in result if c["luck"] == luck]
        return result

    def get_all(self) -> list[dict]:
        """获取全部字库"""
        return self._chars

    @property
    def total(self) -> int:
        return len(self._chars)
