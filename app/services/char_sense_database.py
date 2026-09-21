"""
语境义项库（char_senses）

把「字义」从「字的静态属性」升级为「字 × 出处 → 语境义项」：
同一个字在不同诗句里，含义不同（如「清」在「楚天千里清秋」= 清朗高远，
在「金尊清酒」= 富贵珍美）。

数据文件：data/sense/char_senses.json（list）
    字段：char / entry_id / source_type / senses[list[str]] / note

缺失（文件不存在或该「字×出处」无记录）时统一返回 []，
由调用方回退到静态字义 —— 保证线上不因数据未就绪而崩。
"""

import json
from typing import Optional
from app.core.config import settings


class CharSenseDatabase:
    """字 × 出处 语境义项库"""

    _instance = None
    _index = None  # (char, entry_id) -> rec
    _by_char = None  # char -> list[rec]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """加载数据（文件缺失时降级为空索引，不抛异常）。"""
        self._index = {}
        self._by_char = {}
        path = settings.SENSE_DIR / "char_senses.json"
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            data = data.get("senses") or data.get("data") or []
        for rec in data:
            if not isinstance(rec, dict):
                continue
            char = rec.get("char")
            entry_id = rec.get("entry_id")
            senses = rec.get("senses") or []
            if not char or not entry_id or not isinstance(senses, list):
                continue
            senses = [str(s) for s in senses if s]
            if not senses:
                continue
            clean = {
                "char": char,
                "entry_id": entry_id,
                "source_type": rec.get("source_type", ""),
                "senses": senses,
                "note": rec.get("note", ""),
            }
            self._index[(char, entry_id)] = clean
            self._by_char.setdefault(char, []).append(clean)

    def get_senses(self, char: str, entry_id: str) -> list[str]:
        """取「某字在某出处」的语境义项；无记录返回 []。"""
        if not char or not entry_id:
            return []
        rec = self._index.get((char, entry_id))
        return list(rec["senses"]) if rec else []

    def get_senses_for_char(self, char: str) -> list[dict]:
        """取某字在所有出处里的语境义项记录。"""
        return list(self._by_char.get(char, []))

    @property
    def size(self) -> int:
        return len(self._index)
