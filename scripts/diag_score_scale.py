"""韵味分刻度诊断：为什么推荐结果大多「六七十」。

回答两个问题：
    1. 100 分的量表里，哪几维拿不到、哪几维白送 → 逐维均值 / 得满率
    2. 真实候选的分布长什么样 → 全池分位 + 各输入的池最高分

`miniprogram/utils/score.js` 里「推荐值 = 韵味 ÷ 85 × 100」的 85 就来自本脚本
测出的可达上限；改动评分常量后应重跑本脚本，确认 85 仍是合理锚点。

用法：venv/bin/python scripts/diag_score_scale.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.naming_engine import NamingEngine  # noqa: E402

SURNAMES = ["李", "王", "张", "陈", "林", "苏"]
DATE = (2018, 5, 10)
# 维度 -> 满分（与 app/core/naming_options.py 的 S1_MAX / IMAGERY_MAX 等保持一致）
MAXES = {"provenance": 35, "imagery": 25, "aftertaste": 15,
         "coherence": 10, "surname": 15}

captured: list[list[dict]] = []
_orig = NamingEngine._stratified_sample


def _spy(self, names, k, **kw):
    captured.append(list(names))
    return _orig(self, names, k, **kw)


def main() -> None:
    NamingEngine._stratified_sample = _spy
    eng = NamingEngine()

    agg = {k: [] for k in MAXES}
    totals: list[int] = []
    pool_peaks: list[int] = []
    kind: dict[str, int] = {}

    for s in SURNAMES:
        captured.clear()
        eng.generate_names(s, "male", DATE[0], DATE[1], DATE[2], 12, 0,
                           name_length=2, max_results=6)
        pool = captured[-1]
        pool_peaks.append(max(n["scores"]["yunwei"] for n in pool))
        for n in pool:
            d = n["scores"]["yunwei_detail"]
            totals.append(d["total"])
            agg["provenance"].append(d["provenance"])
            agg["imagery"].append(d["imagery"])
            agg["aftertaste"].append(d["aftertaste"])
            agg["coherence"].append(d["coherence"])
            agg["surname"].append(d["surname_coherence"]["total"])
            kind[d["cohesion"]] = kind.get(d["cohesion"], 0) + 1

    n = len(totals)
    print(f"【1】维度拆解  样本 n={n}  均值={statistics.mean(totals):.1f}  "
          f"最高={max(totals)}")
    print(f"  {'维度':<12}{'满分':>5}{'均值':>7}{'最高':>6}{'得满率':>8}  说明")
    notes = {
        "provenance": "同源分档，annotated 字对能给满",
        "imagery": "命中 1 个意象词 +4，一条出处通常只标 1~3 个",
        "aftertaste": "义项数 ×4 封顶 15，几乎人人拿满 → 无区分度",
        "coherence": "部首同族 10 / 意象交集或动名结构 5",
        "surname": "要「姓+名」在原文成词，常见姓氏基本为 0",
    }
    for k, mx in MAXES.items():
        v = agg[k]
        full = sum(1 for x in v if x >= mx)
        print(f"  {k:<12}{mx:>5}{statistics.mean(v):>7.1f}{max(v):>6}"
              f"{full / len(v):>7.0%}  {notes[k]}")

    totals.sort()

    def pct(q: float) -> int:
        return totals[min(len(totals) - 1, int(len(totals) * q))]

    print(f"\n【2】全池分布  min={totals[0]} p10={pct(0.1)} p50={pct(0.5)} "
          f"p90={pct(0.9)} p99={pct(0.99)} max={totals[-1]}")
    print("  各输入池最高分：", pool_peaks)
    print(f"\n  可达上限（实测最高）= {totals[-1]} → miniprogram/utils/score.js 的 CEIL")
    print("  组合成立度分布：", kind)
    print("\n结论：100 分里姓氏 S(15) 恒空、余味 L(15) 白送，"
          "真实分布被压在 55~77，故展示刻度按可达上限折算。")


if __name__ == "__main__":
    main()
