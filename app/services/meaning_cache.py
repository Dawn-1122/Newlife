"""
LLM 寓意缓存（内存 LRU + 可选文件缓存）

缓存 key = full_name + gender + 生辰签名 + citation。
命中缓存直接返回，避免详情页重复调用 LLM（费用控制）。
"""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Optional
from app.core.config import settings


class MeaningCache:
    """LLM 寓意缓存（进程内单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        self._mem: OrderedDict[str, dict] = OrderedDict()
        self._max_size = 512
        self._cache_dir: Path = settings.MEANING_CACHE_DIR

    # ── key 构建 ──

    @staticmethod
    def build_key(
        full_name: str,
        gender: str,
        bazi_signature: Optional[str],
        citation: Optional[str],
    ) -> str:
        """构建缓存 key（可读字符串，供内存 LRU 使用）。"""
        gender = gender or ""
        bazi_signature = bazi_signature or ""
        citation = citation or ""
        return f"{full_name}|{gender}|{bazi_signature}|{citation}"

    @staticmethod
    def _hash_key(key: str) -> str:
        """对 key 做稳定哈希，作为文件缓存文件名。"""
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    # ── 读写 ──

    def get(self, key: str) -> Optional[dict]:
        """读缓存：先内存，再文件（命中文件则回填内存）。"""
        if key in self._mem:
            # 命中后移动到末尾（LRU）
            value = self._mem.pop(key)
            self._mem[key] = value
            return value

        value = self._read_file(key)
        if value is not None:
            self._mem[key] = value
            self._evict_if_needed()
            return value
        return None

    def set(self, key: str, value: dict) -> None:
        """写缓存：内存 + 文件。"""
        self._mem[key] = value
        self._evict_if_needed()
        self._write_file(key, value)

    # ── 内部实现 ──

    def _evict_if_needed(self) -> None:
        while len(self._mem) > self._max_size:
            self._mem.popitem(last=False)

    def _file_path(self, key: str) -> Path:
        return self._cache_dir / f"{self._hash_key(key)}.json"

    def _read_file(self, key: str) -> Optional[dict]:
        try:
            path = self._file_path(key)
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_file(self, key: str, value: dict) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._file_path(key)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
        except OSError:
            # 文件写失败不影响主流程（内存缓存仍生效）
            pass

    def clear(self) -> None:
        """清空内存缓存（文件缓存保留）。"""
        self._mem.clear()
