"""
诗词库扩充共享工具（供 normalize/annotator/validate/merge 复用）。

提供：
- load_char_map()     字库 char -> 记录
- load_lucky_chars()  字库中 luck=吉 的字集合
- load_blacklist()    最终黑名单 = 字库 luck=凶 ∪ data/dict/blacklist.json 人工补充
- iter_corpus()       遍历 .corpus 语料目录下的 JSON 文件
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHARS_PATH = PROJECT_ROOT / "data" / "dict" / "chars.json"
BLACKLIST_PATH = PROJECT_ROOT / "data" / "dict" / "blacklist.json"


def load_char_map() -> dict[str, dict]:
    """加载字库：char -> 记录。"""
    with open(CHARS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["char"]: c for c in data["chars"]}


def load_lucky_chars() -> set[str]:
    """字库中 luck=吉 的字集合。"""
    char_map = load_char_map()
    return {ch for ch, c in char_map.items() if c.get("luck") == "吉"}


def load_blacklist() -> set[str]:
    """最终负面字黑名单 = 字库 luck=凶 ∪ 人工补充 blacklist.json。"""
    char_map = load_char_map()
    blacklist = {ch for ch, c in char_map.items() if c.get("luck") == "凶"}
    if BLACKLIST_PATH.exists():
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        blacklist.update(data.get("chars", []))
    return blacklist


def iter_corpus_json(corpus_dir: Path, rel_glob: str = "**/*.json") -> Iterator[Path]:
    """遍历语料目录下的 JSON 文件（跳过 .git 与超大目录可自行过滤）。"""
    if not corpus_dir.exists():
        return
    for path in sorted(corpus_dir.glob(rel_glob)):
        if ".git" in path.parts:
            continue
        yield path
