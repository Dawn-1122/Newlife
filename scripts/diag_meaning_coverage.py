"""
期许/气质的语料承载诊断

回答一个问题：14 个期许里，哪些是「有字表但语料撑不住」的？

字表（app/core/meaning_culture.py）保证每个期许至少 8 个字，
但**字在表里 ≠ 能在名字里出现**：一个文化字如果只在 1~2 首诗里出现，
它就很难被抽到；如果它压根不在语料里，字表就是空头支票
（后者已由 test_meaning_culture.test_culture_chars_are_in_candidate_pool 挡住）。

本脚本统计每个期许的「承载强度」，用于决定补语料时该补哪些主题：

- 富余：字均覆盖 ≥ COMFORT 首 —— 不用动
- 偏薄：字均覆盖 <  COMFORT 首 —— 补语料优先
- 空壳：有字在语料里完全不出现 —— 属硬伤（测试应已拦住，这里再报一次）

用法：
    venv/bin/python scripts/diag_meaning_coverage.py
    venv/bin/python scripts/diag_meaning_coverage.py --top 6
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.meaning_culture import (  # noqa: E402
    MEANING_CULTURE_CHARS,
    STYLE_CULTURE_CHARS,
)
from app.core.naming_options import MEANING_OPTIONS, STYLE_OPTIONS  # noqa: E402

POETRY_DIR = PROJECT_ROOT / "data" / "poetry"

# 单字至少被这么多首诗推荐过，才算「抽得到」（下面叫「可用字」）。
# 取 3：k=6 一批只从几十个候选里取，覆盖 1~2 首的字基本轮不到；
# 而语料里 514 个字只出现 ≤2 首，把门槛抬到 5 会让「窄」变成常态、失去区分。
THIN = 3


def load_poems() -> list[dict]:
    # 与 PoetryDatabase._load 同一口径：主库 + 所有 poetry_extra*.json
    poems: list[dict] = []
    for path in sorted(POETRY_DIR.glob("poetry*.json")):
        if path.name in ("poetry.schema.json",):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        poems += (data.get("poems") if isinstance(data, dict) else data) or []
    return poems


def char_counts(poems: list[dict]) -> Counter:
    """每个字被多少首诗「推荐」过 —— 与引擎取字的口径一致（recommend_chars）。"""
    counts: Counter = Counter()
    for p in poems:
        for ch in p.get("recommend_chars") or []:
            counts[ch] += 1
    return counts


def report(title: str, table: dict, names: dict, counts: Counter) -> None:
    print(f"\n{'=' * 84}\n{title}\n{'=' * 84}")
    rows = []
    for code, chars in table.items():
        covered = [counts.get(c, 0) for c in chars]
        # 「可用字」= 至少被 THIN 首诗推荐过的字。只数平均值会骗人：
        # 健康类里松/鹤/柏各几十首，把康(1 首)/健(2 首)的稀薄摊平了，
        # 于是「字均 6.1，富余」——可实际出名字时反复出现的还是那三个字。
        usable = [c for c, n in zip(chars, covered) if n >= THIN]
        empty = [c for c, n in zip(chars, covered) if n == 0]
        thin = [c for c, n in zip(chars, covered) if 0 < n < THIN]
        rows.append((len(usable), code, len(chars), empty, thin))
    rows.sort()  # 可用字最少的排在最前

    print(f"{'code':<12}{'名':<10}{'字表':>5}{'可用字':>7}{'占比':>7}  状态")
    print("-" * 84)
    for usable_n, code, n, empty, thin in rows:
        share = usable_n / n if n else 0
        if share >= 0.6:
            status = "宽"
        elif share >= 0.4:
            status = "中"
        else:
            status = "窄"
        label = (names.get(code) or {}).get("name", code)
        print(f"{code:<12}{label:<10}{n:>5}{usable_n:>7}{share:>7.0%}  {status}"
              + (f"  空壳：{''.join(empty)}" if empty else ""))
    print()
    thin_rows = [(u, c, n, e, t) for u, c, n, e, t in rows if u / n < 0.6]
    if thin_rows:
        print(f"可用字占比 < 60% 的（补语料优先）：")
        for usable_n, code, n, empty, thin in thin_rows:
            label = (names.get(code) or {}).get("name", code)
            print(f"  {code:<12}{label:<10}可用 {usable_n}/{n}，"
                  f"稀薄字（<{THIN} 首）：{''.join(thin) or '无'}")


def main() -> int:
    poems = load_poems()
    counts = char_counts(poems)
    pool = set(counts)
    print(f"语料：{len(poems)} 首，可推荐字 {len(pool)} 个")

    report("期许（14）", MEANING_CULTURE_CHARS, MEANING_OPTIONS, counts)
    report("气质（8）", STYLE_CULTURE_CHARS, STYLE_OPTIONS, counts)

    # 全局最稀薄的字：补语料时可以照着这些字找诗
    rare = sorted(((n, c) for c, n in counts.items() if n <= 2))
    print(f"\n全语料里只出现 ≤2 首的字：{len(rare)} 个")
    print("  " + "".join(c for n, c in rare[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
