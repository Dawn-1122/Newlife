"""名字感闸门的效果与产能诊断。

回答两个问题：
1. 产出里的「土名」还剩多少（按 pair_taste 分级统计）；
2. 屏蔽 569 个字对后，池子还够不够「换一批」——同输入连翻 12 批的去重率。

用法：venv/bin/python scripts/diag_taste_impact.py
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.naming_engine import NamingEngine  # noqa: E402

INPUTS = [
    ("林", "female", None, None),
    ("林", "male", None, None),
    ("苏", "female", "elegant", ["温柔", "聪慧"]),
    ("苏", "male", "bold", ["志向", "宽广"]),
    ("叶", "female", "fresh", None),
    ("叶", "male", None, ["坚韧"]),
    ("顾", "female", "classic", None),
    ("顾", "male", "elegant", None),
    ("沈", "female", None, ["清雅"]),
    ("沈", "male", "classic", ["学识"]),
    ("江", "female", "fresh", ["明媚"]),
    ("江", "male", "bold", ["大气"]),
]


def run(seed: int = 20261021, batches: int = 12, per: int = 6) -> None:
    engine = NamingEngine()
    random.seed(seed)
    total = Counter()
    all_names: set[str] = set()
    for surname, gender, style, meanings in INPUTS:
        seen: list[str] = []
        new_by_batch: list[int] = []
        for _ in range(batches):
            r = engine.generate_names(
                surname=surname, gender=gender, name_length=2,
                max_results=per, use_bazi=False, style=style,
                meanings=meanings,
            )
            got = [n["given_name"] for n in r["names"]]
            fresh = [g for g in got if g not in seen]
            new_by_batch.append(len(fresh))
            seen.extend(got)
            total.update(
                engine._pair_taste(*n["given_name"]) for n in r["names"]
                if len(n["given_name"]) == 2
            )
            all_names.update(got)
        distinct = len(set(seen))
        print(f"  {surname}/{gender:<6s} style={str(style):<8s} "
              f"12 批新名数 {new_by_batch} → 去重 {distinct}/{len(seen)}")
    print()
    n = sum(total.values())
    print(f"[名字感分布] 共 {n} 个名字：", end="")
    for s in (5, 4, 3, 1):
        c = total.get(s, 0)
        print(f"  {s} 分 {c}（{c * 100 // max(n, 1)}%）", end="")
    print(f"\n[唯一名字] {len(all_names)} 个")


def pickable() -> None:
    engine = NamingEngine()
    for surname, gender in (("林", "female"), ("苏", "male")):
        t = engine.pickable_chars(surname=surname, gender=gender)
        print(f"[字表] {surname}/{gender}: 池内 {t['total']} 字，"
              f"可行 {t['feasible']} 字，返回 {t['returned']} 字")


if __name__ == "__main__":
    print("[产能] 同输入连翻 12 批（每批 6 名）")
    run()
    print()
    pickable()
