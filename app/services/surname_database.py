"""
姓氏字典服务

提供姓氏的字义/意象查询，供韵味评分 S2 姓氏协调维度评估
「姓 + 名」的字义/意象呼应。姓氏未收录时返回 None（S2=0，不影响排序）。
"""

import json
from typing import Optional
from app.core.config import settings


class SurnameDatabase:
    """姓氏字典"""

    _instance = None
    _surnames = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        path = settings.DICT_DIR / settings.SURNAME_DB_FILE
        self._surnames: dict[str, dict] = {}
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("surnames", []):
            self._surnames[item["char"]] = {
                "char": item.get("char", ""),
                "pinyin": item.get("pinyin", ""),
                "meaning": item.get("meaning", ""),
                "imagery": item.get("imagery", []),
            }

    def get_surname(self, char: str) -> Optional[dict]:
        """查询单个姓氏的字义/意象，未收录返回 None。"""
        return self._surnames.get(char)

    @property
    def total(self) -> int:
        return len(self._surnames)
