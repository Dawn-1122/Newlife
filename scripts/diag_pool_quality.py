"""候选池质量诊断：拆解「同源名 vs 单字名」的比例与得分，定位弱尾来源。

用于验证/复现 STRATIFY_QUALITY_BAND 的必要性：
    同源名（双字同出一源，出处分 P=35）均分 63~64，单字名（P=20）均分仅 44~47。
若此项诊断显示单字名均分接近同源名，说明源数据已扩充，可以考虑放宽带宽。

用法：venv/bin/python scripts/diag_pool_quality.py
"""
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


def main() -> None:
    NamingEngine._stratified_sample = _spy
    eng = NamingEngine()

    print("【1】候选池出处结构（进入分层抽样前）")
    print(f"{'生日':<14}{'池':>5}{'同源':>6}{'单字':>6}"
          f"{'同源均分':>9}{'单字均分':>9}{'池max':>7}{'池p50':>7}")
    for (y, m, d) in CASES:
        eng.generate_names("李", "male", y, m, d, 12, 0,
                           name_length=2, max_results=30)
        pool = captured[-1]
        by: dict[str, list[float]] = collections.defaultdict(list)
        for n in pool:
            detail = n["scores"].get("yunwei_detail") or {}
            by["同源" if detail.get("same_source") else "单字"].append(
                n["scores"]["yunwei"]
            )
        scores = sorted(n["scores"]["yunwei"] for n in pool)
        avg = lambda key: statistics.fmean(by[key]) if by[key] else 0  # noqa: E731
        print(f"{y}-{m:02d}-{d:02d}   {len(pool):>5}{len(by['同源']):>6}"
              f"{len(by['单字']):>6}{avg('同源'):>9.1f}{avg('单字'):>9.1f}"
              f"{scores[-1]:>7.0f}{scores[len(scores) // 2]:>7.0f}")

    print()
    print("【2】同源池是否能靠组合预算扩大（结论：不能）")
    NamingEngine._stratified_sample = _orig
    print(f"{'随机预算':>9}{'组合上限':>9}  " +
          "  ".join(f"{y}-{m:02d}" for y, m, _ in CASES))
    for rbf, ccf in [(20, 40), (80, 40), (160, 200)]:
        NamingEngine.RANDOM_BUDGET_FACTOR = rbf
        NamingEngine.COMPOSE_CAP_FACTOR = ccf
        NamingEngine._stratified_sample = _spy
        sames = []
        for (y, m, d) in CASES:
            eng.generate_names("李", "male", y, m, d, 12, 0,
                               name_length=2, max_results=30)
            sames.append(sum(
                1 for n in captured[-1]
                if (n["scores"].get("yunwei_detail") or {}).get("same_source")))
        print(f"{rbf:>9}{max(30 * ccf, 600):>9}  " +
              "  ".join(f"{s:>6}" for s in sames))


if __name__ == "__main__":
    main()
