"""性别维度的产出口径对比：男女请求各自的有效出处池、同源池与结果质量。"""
from __future__ import annotations

import collections
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.naming_engine import NamingEngine  # noqa: E402

CASES = [(2018, 5, 10), (2020, 8, 20), (2016, 2, 3), (2014, 11, 7)]
captured: list[list[dict]] = []
_orig = NamingEngine._stratified_sample


def _spy(self, names, k, **kw):
    captured.append(list(names))
    return _orig(self, names, k, **kw)


NamingEngine._stratified_sample = _spy
eng = NamingEngine()

print("【出处池口径】")
for g in ("male", "female"):
    ents = eng.poetry_db.get_by_gender(g) + eng.source_db.get_by_gender(g)
    gg = collections.Counter(e.get("gender") for e in ents)
    print(f"  {g:7} 匹配出处 {len(ents):>4} 条，其中 gender 分布 {dict(gg)}")

print()
print("【起名产出口径】")
print(f"{'性别':<7}{'池':>6}{'同源':>6}{'池p50':>7}{'结果min':>8}{'结果中位':>9}")
for g in ("male", "female"):
    pools, sames, p50, rmin, rmed = [], [], [], [], []
    for (y, m, d) in CASES:
        r = eng.generate_names("林", g, y, m, d, 12, 0,
                               name_length=2, max_results=30)
        pool = captured[-1]
        sc = sorted(n["scores"]["yunwei"] for n in pool)
        pools.append(len(pool))
        p50.append(sc[len(sc) // 2])
        sames.append(sum(1 for n in pool
                         if (n["scores"].get("yunwei_detail") or {})
                         .get("same_source")))
        rs = [n["scores"]["yunwei"] for n in r["names"]]
        rmin.append(min(rs))
        rmed.append(statistics.median(rs))
    print(f"{g:<7}{statistics.fmean(pools):>6.0f}{statistics.fmean(sames):>6.0f}"
          f"{statistics.fmean(p50):>7.0f}{min(rmin):>8.0f}{statistics.fmean(rmed):>9.0f}")
