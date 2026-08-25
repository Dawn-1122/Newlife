"""
T2 · 数据结构升级与迁移

把现有 42 首 poetry.json(v1) 迁移到 v2：
- 补 id（按顺序 poem_0001 … poem_0042，稳定可重跑）
- 补 emotion（规则初判 喜庆/中性/哀伤）
- 补 citation / original_text(null) / provenance("manual/legacy") / tags([])
- source 规范化：周易/大学/中庸 归入大类「经史子集」，典籍名下移到 title/citation
- 数据修复：剔除推荐字中的「凶」字（如 桃夭 的「夭」）；emotion=哀伤 的条目清空推荐字

幂等：重复运行结果一致（id 由顺序决定、凶字剔除与哀伤清空均为幂等操作）。
注意：本脚本仅用于「旧 42 首 → v2」这一步；合并新语料请使用 merge_poetry.py。

用法：
    venv/bin/python scripts/migrate_poetry.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.constants import SAD_POETRY_TITLES

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POETRY_PATH = PROJECT_ROOT / "data" / "poetry" / "poetry.json"
CHARS_PATH = PROJECT_ROOT / "data" / "dict" / "chars.json"

# 6 大类枚举（v2）
SOURCE_CLASSES = ("诗经", "楚辞", "唐诗", "宋词", "汉魏古诗", "经史子集")

# 典籍名 → 大类（规范化映射）
SOURCE_NORMALIZE = {
    "周易": "经史子集",
    "大学": "经史子集",
    "中庸": "经史子集",
}

# 情感初判关键词（作用在 imagery + scene 上，标题黑名单优先）
HAPPY_KEYWORDS = (
    "喜", "乐", "欢", "团圆", "祝愿", "得意", "吉", "良", "芳", "美好",
    "祥和", "昌盛", "荣", "嘉", "欣", "悦", "瑞", "泰", "安",
)
SAD_KEYWORDS = (
    "离", "伤", "愁", "悲", "寒", "冷", "凄", "凋", "零", "苦",
    "恨", "怨", "亡", "泪", "孤", "寂", "残", "断", "戚", "惨",
)


def load_char_map() -> dict[str, dict]:
    """加载字库，用于识别「凶」字。"""
    with open(CHARS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["char"]: c for c in data["chars"]}


def build_citation(source: str, title: str) -> str:
    """由 source + title 拼出处标注。"""
    if source in ("诗经", "楚辞"):
        return f"《{source}·{title}》"
    return f"《{title}》"


def classify_emotion(title: str, imagery: list[str], scene: str) -> str:
    """规则初判情感（标题黑名单 > 喜庆 > 哀伤 > 中性）。"""
    if any(sad in title for sad in SAD_POETRY_TITLES):
        return "哀伤"
    blob = " ".join(imagery or []) + " " + (scene or "")
    if any(k in blob for k in HAPPY_KEYWORDS):
        return "喜庆"
    if any(k in blob for k in SAD_KEYWORDS):
        return "哀伤"
    return "中性"


def migrate_poem(poem: dict, index: int, char_map: dict[str, dict]) -> dict:
    """迁移单条诗词到 v2。"""
    source = poem.get("source", "")
    title = poem.get("title", "")

    # source 规范化（周易/大学/中庸 → 经史子集）
    new_source = SOURCE_NORMALIZE.get(source, source)
    if new_source not in SOURCE_CLASSES:
        # 未知来源兜底（理论上不会发生，稳妥起见归入经史子集前保留原值）
        new_source = source

    emotion = classify_emotion(
        title, poem.get("imagery", []), poem.get("scene", "")
    )

    recommend_chars = list(poem.get("recommend_chars", []))
    # 数据修复 1：剔除「凶」字（如 桃夭 的「夭」）
    recommend_chars = [
        ch for ch in recommend_chars
        if not (ch in char_map and char_map[ch].get("luck") == "凶")
    ]
    # 数据修复 2：哀伤条目清空推荐字（校验 R5 一致性）
    if emotion == "哀伤":
        recommend_chars = []

    return {
        "id": f"poem_{index:04d}",
        "source": new_source,
        "title": title,
        "author": poem.get("author", "佚名"),
        "dynasty": poem.get("dynasty", ""),
        "text": poem.get("text", ""),
        "original_text": poem.get("original_text"),
        "citation": build_citation(new_source, title),
        "recommend_chars": recommend_chars,
        "emotion": emotion,
        "imagery": list(poem.get("imagery", [])),
        "gender": poem.get("gender", "中"),
        "scene": poem.get("scene", ""),
        "tags": list(poem.get("tags", [])),
        "provenance": poem.get("provenance", "manual/legacy"),
    }


def main() -> None:
    char_map = load_char_map()

    with open(POETRY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    old_poems = data.get("poems", [])
    migrated = [
        migrate_poem(p, i + 1, char_map) for i, p in enumerate(old_poems)
    ]

    # 按 6 大类统计分布
    source_distribution: dict[str, int] = {}
    for p in migrated:
        s = p["source"]
        source_distribution[s] = source_distribution.get(s, 0) + 1

    output = {
        "version": "2.0",
        "total": len(migrated),
        "source_distribution": source_distribution,
        "poems": migrated,
    }

    with open(POETRY_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[migrate_poetry] 迁移完成: {POETRY_PATH}")
    print(f"  总计 {len(migrated)} 首，来源分布: {source_distribution}")
    sad = [p["id"] for p in migrated if p["emotion"] == "哀伤"]
    print(f"  哀伤条目 {len(sad)}: {sad}")


if __name__ == "__main__":
    main()
