"""
T4 · 合并入库

把「旧 42 首(v2) + LLM 标注结果」合并成最终 poetry.json v2。

流程：
1. 读 poetry.json（已迁移的 v2 旧数据）
2. 读 annotated.jsonl（LLM 标注，按 raw id 关联）
3. 读 raw_corpus.jsonl（补元数据：source/title/author/dynasty/text/original_text/citation/provenance）
4. 分配稳定 id（poem_XXXX，接在旧数据之后）
5. 按 (source,title,text) 去重（跳过与旧数据重复的）
6. 交叉校验（R1~R11），有硬错误则不产出
7. 写回 poetry.json v2（重算 total / source_distribution）

用法：
    venv/bin/python scripts/merge_poetry.py
    venv/bin/python scripts/merge_poetry.py --annotated data/poetry/annotated.jsonl --raw data/poetry/raw_corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from poetry_utils import PROJECT_ROOT, load_char_map, load_blacklist
from validate_poetry import validate_poems

DEFAULT_POETRY = PROJECT_ROOT / "data" / "poetry" / "poetry.json"
DEFAULT_ANNOTATED = PROJECT_ROOT / "data" / "poetry" / "annotated.jsonl"
DEFAULT_RAW = PROJECT_ROOT / "data" / "poetry" / "raw_corpus.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def next_id(existing: list[dict]) -> int:
    """计算下一个 poem 序号（接在现有最大 id 之后）。"""
    max_seq = 0
    for p in existing:
        pid = p.get("id", "")
        if pid.startswith("poem_") and pid[5:].isdigit():
            max_seq = max(max_seq, int(pid[5:]))
    return max_seq + 1


def build_new_poem(raw: dict, ann: dict, seq: int) -> dict:
    """把 raw 元数据 + LLM 标注合并成 v2 PoetryEntry。"""
    return {
        "id": f"poem_{seq:04d}",
        "source": raw.get("source", ""),
        "title": raw.get("title", ""),
        "author": raw.get("author", "佚名"),
        "dynasty": raw.get("dynasty", ""),
        "text": raw.get("text", ""),
        "original_text": raw.get("original_text"),
        "citation": raw.get("citation", ""),
        "recommend_chars": list(ann.get("recommend_chars", [])),
        "emotion": ann.get("emotion", "中性"),
        "imagery": list(ann.get("imagery", [])),
        "gender": ann.get("gender", "中"),
        "scene": ann.get("scene", ""),
        "tags": list(ann.get("imagery", [])),
        "provenance": raw.get("provenance", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="合并诗词库")
    parser.add_argument("--poetry", default=str(DEFAULT_POETRY))
    parser.add_argument("--annotated", default=str(DEFAULT_ANNOTATED))
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    args = parser.parse_args()

    poetry_path = Path(args.poetry)
    with open(poetry_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    existing = data.get("poems", [])

    annotated = load_jsonl(Path(args.annotated))
    raw_entries = load_jsonl(Path(args.raw))
    raw_map = {e["id"]: e for e in raw_entries}

    if not annotated:
        print("[merge] annotated.jsonl 为空，无新条目可合并")
        sys.exit(1)

    # 去重集合
    existing_keys = {(p["source"], p["title"], p["text"]) for p in existing}

    seq = next_id(existing)
    new_poems: list[dict] = []
    skipped = 0
    missing_meta = 0
    for ann in annotated:
        raw = raw_map.get(ann["id"])
        if not raw:
            missing_meta += 1
            print(f"[merge] 缺元数据，跳过: {ann['id']}")
            continue
        key = (raw["source"], raw["title"], raw["text"])
        if key in existing_keys:
            skipped += 1
            continue
        existing_keys.add(key)
        new_poems.append(build_new_poem(raw, ann, seq))
        seq += 1

    merged = existing + new_poems

    # 交叉校验（有硬错误不产出）
    char_map = load_char_map()
    blacklist = load_blacklist()
    report = validate_poems(merged, char_map, blacklist)

    print(f"[merge] 旧 {len(existing)} 首 + 新 {len(new_poems)} 首"
          f"（跳过重复 {skipped}，缺元数据 {missing_meta}）→ 共 {len(merged)} 首")
    print(f"[merge] 校验：硬错误 {len(report['errors'])}，警告 {len(report['warnings'])}")

    for e in report["errors"]:
        print(f"  [ERROR] {e['rule']} {e['id']}《{e['title']}》{e['message']}")

    if report["errors"]:
        print("[merge] 校验未通过，不产出 poetry.json（请先修复）")
        sys.exit(1)

    # 重算分布
    source_distribution: dict[str, int] = {}
    for p in merged:
        s = p["source"]
        source_distribution[s] = source_distribution.get(s, 0) + 1

    output = {
        "version": "2.0",
        "total": len(merged),
        "source_distribution": source_distribution,
        "poems": merged,
    }
    with open(poetry_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[merge] 已写入 {poetry_path}")
    print(f"  来源分布: {source_distribution}")


if __name__ == "__main__":
    main()
