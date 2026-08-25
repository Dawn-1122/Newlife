"""
试点选诗：从 raw_corpus.jsonl 中精选约 N 首干净、适合起名的摘句（试点专用）。

策略：
1. 剔除引用残片（含《》「」『』曰 云 等）
2. 剔除明显负面短语
3. 按 (source, title) 去重（每篇保留评分最高的一条摘句）
4. 跨 6 大类轮询选取，保证覆盖

产物：data/poetry/pilot_corpus.jsonl（是 raw_corpus.jsonl 的子集，id 保持一致）。

用法：
    venv/bin/python scripts/select_pilot.py --n 52
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from poetry_utils import PROJECT_ROOT

DEFAULT_RAW = PROJECT_ROOT / "data" / "poetry" / "raw_corpus.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "data" / "poetry" / "pilot_corpus.jsonl"

# 明显负面/不适合起名的短语（试点阶段人工补充的粗筛）
NEGATIVE_PHRASES = (
    "消黯", "无人传", "碎石", "踯躅", "无味", "强饮", "强乐", "消魂",
    "离绪", "惹起", "心事", "一场", "独怆然", "肠断", "泪", "愁", "恨",
    "怨", "悲", "凄", "戚", "惨", "凋", "零落", "残", "断肠", "伤春",
    "送别", "出征", "夜吼", "风夜吼",
)


def is_clean(entry: dict) -> bool:
    text = entry.get("text", "")
    if any(ch in text for ch in "《》「」『』曰云"):
        return False
    if any(kw in text for kw in NEGATIVE_PHRASES):
        return False
    return True


def select(raw_entries: list[dict], n: int) -> list[dict]:
    # 1. 清洗
    clean = [e for e in raw_entries if is_clean(e)]
    # 2. 按 (source, title) 去重，保留顺序中第一条（评分更高）
    by_key: dict[tuple, dict] = {}
    for e in clean:
        key = (e["source"], e["title"])
        if key not in by_key:
            by_key[key] = e
    deduped = list(by_key.values())

    # 3. 轮询选取
    buckets: dict[str, list[dict]] = defaultdict(list)
    for e in deduped:
        buckets[e["source"]].append(e)

    result: list[dict] = []
    sources = sorted(buckets.keys())
    row = 0
    while len(result) < n:
        added = False
        for s in sources:
            if row < len(buckets[s]):
                result.append(buckets[s][row])
                added = True
                if len(result) >= n:
                    break
        if not added:
            break
        row += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="试点选诗")
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--n", type=int, default=52)
    args = parser.parse_args()

    entries = [json.loads(l) for l in open(args.raw, encoding="utf-8") if l.strip()]
    picked = select(entries, args.n)

    out = Path(args.out)
    with open(out, "w", encoding="utf-8") as f:
        for e in picked:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    from collections import Counter
    dist = Counter(e["source"] for e in picked)
    print(f"[select_pilot] 从 {len(entries)} 条中精选 {len(picked)} 条 → {out}")
    print(f"  来源分布: {dict(dist)}")


if __name__ == "__main__":
    main()
