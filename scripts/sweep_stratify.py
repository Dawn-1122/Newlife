"""分层抽样参数扫描：用神加分 × 温度 × 质量带宽 对
「尾部韵味 / 八字匹配 / 多样性」的联合影响。

用法：venv/bin/python scripts/sweep_stratify.py
"""
from __future__ import annotations

import collections
import itertools
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.naming_engine import NamingEngine  # noqa: E402

CASES = [
    (2018, 5, 10), (2020, 8, 20), (2016, 2, 3), (2014, 11, 7),
    (2019, 3, 15), (2017, 7, 22), (2015, 9, 1), (2021, 6, 18),
    (2013, 4, 25), (2022, 1, 12),
]
TOP = 30


def run(engine, yong_bonus, temperature, band):
    NamingEngine.STRATIFY_YONG_BONUS = yong_bonus
    NamingEngine.STRATIFY_TEMPERATURE = temperature
    NamingEngine.STRATIFY_QUALITY_BAND = band

    all_scores, per_input, visitor = [], [], collections.Counter()
    bazi_hit = bazi_tot = weak = 0
    for (y, m, d) in CASES:
        r = engine.generate_names("李", "male", y, m, d, 12, 0,
                                  name_length=2, max_results=TOP)
        names = r["names"]
        try:
            yong = engine.bazi.generate_bazi(
                y, m, d, 12, 0, "male")["xiyong"]["yong_wuxing"]
        except Exception:
            yong = None
        s = set()
        for n in names:
            v = n["scores"]["yunwei"]
            all_scores.append(v)
            weak += 1 if v < 50 else 0
            s.add(n["full_name"])
            visitor[n["full_name"]] += 1
            if yong:
                bazi_tot += 1
                if any(c.get("wuxing") == yong for c in n["chars_info"]):
                    bazi_hit += 1
        per_input.append(s)

    jac = []
    for a, b in itertools.combinations(per_input, 2):
        jac.append(len(a & b) / len(a | b) if (a | b) else 0.0)

    sc = sorted(all_scores)
    n = len(sc)
    return {
        "min": sc[0], "p5": sc[max(0, int(n * 0.05) - 1)],
        "p10": sc[max(0, int(n * 0.1) - 1)],
        "median": statistics.median(sc), "mean": statistics.fmean(sc),
        "bazi": bazi_hit / bazi_tot if bazi_tot else 0,
        "jac": statistics.fmean(jac) if jac else 0,
        "visitor": visitor.most_common(1)[0][1] if visitor else 0,
        "uniq": len({x for s in per_input for x in s}),
        "weak": weak,
    }


def main():
    engine = NamingEngine()
    print(f"{'用神':>5}{'温度':>5}{'带宽':>5}{'min':>5}{'p5':>5}{'p10':>5}"
          f"{'中位':>6}{'均值':>6}{'八字':>7}{'重合':>7}{'常客':>5}"
          f"{'不同名':>7}{'<50分':>6}")
    print("-" * 80)
    combos = itertools.product([60.0], [36.0, 44.0, 52.0, 64.0], [17.0, 18.0, 20.0])
    for yb, tp, bd in combos:
        m = run(engine, yb, tp, bd)
        print(f"{yb:>5.0f}{tp:>5.0f}{bd:>5.0f}{m['min']:>5.0f}{m['p5']:>5.0f}"
              f"{m['p10']:>5.0f}{m['median']:>6.0f}{m['mean']:>6.1f}"
              f"{m['bazi']:>6.0%}{m['jac']:>7.1%}{m['visitor']:>5}"
              f"{m['uniq']:>7}{m['weak']:>6}")


if __name__ == "__main__":
    main()
