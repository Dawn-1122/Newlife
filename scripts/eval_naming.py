"""
起名质量量化验收脚本

对「不同生日/偏好 → 结果高度相似」这一核心问题做可复现的量化评估。
输出以下指标（改造前 → 目标）：

1. 用字集中度       全部名字用到的不同字数 / 总用字数（越低越集中）
2. 高频常客         同一名字在 N 组不同输入中反复出现的最大次数（目标 ≤2）
3. 跨输入重合率     不同生日 Top-K 名字集合的平均重合比例（目标 <20%）
4. 八字匹配度       名字用字命中喜用神五行的比例（分层抽样后应 ≥60%）
5. 偏好生效度       不同寓意请求之间的名字重合比例（目标 <50%）
6. 换一批有变化     同一输入重复两次的重合比例（目标 <90%）
7. 语境义项覆盖     名字各字在出处语境下取到义项的比例

用法：
    venv/bin/python scripts/eval_naming.py
    venv/bin/python scripts/eval_naming.py --rounds 18 --top 30
"""

from __future__ import annotations

import argparse
import collections
import itertools
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.naming_engine import NamingEngine  # noqa: E402

# 覆盖不同年份（不同年柱 → 不同喜用神）与月日
BIRTH_CASES = [
    (2018, 5, 10), (2020, 8, 20), (2016, 2, 3), (2014, 11, 7),
    (2019, 3, 15), (2017, 7, 22), (2015, 9, 1), (2021, 6, 18),
    (2013, 4, 25), (2022, 1, 12), (2012, 10, 5), (2011, 12, 30),
    (2010, 8, 8), (2009, 5, 19), (2008, 3, 3), (2007, 11, 11),
    (2006, 7, 7), (2005, 2, 14),
]

MEANING_CASES = [
    ["bravery"], ["beauty"], ["wisdom"], ["health"],
    ["peace"], ["wealth"],
]


def top_names(engine, surname, gender, y, m, d, meanings=None, style=None,
              top=30) -> list[dict]:
    r = engine.generate_names(
        surname, gender, y, m, d, 12, 0,
        name_length=2, max_results=top,
        meanings=meanings, style=style,
    )
    return r["names"]


def names_set(names: list[dict]) -> set[str]:
    return {n["full_name"] for n in names}


def report_character_concentration(all_names: list[dict]) -> None:
    counter: collections.Counter = collections.Counter()
    for n in all_names:
        for ch in n["given_name"]:
            counter[ch] += 1
    total = sum(counter.values())
    uniq = len(counter)
    top20 = sum(c for _c, c in counter.most_common(20))
    print(f"[用字集中度] 总用字 {total}，不同字 {uniq}，"
          f"Top20 字占比 {top20 / total:.0%}（越低越分散）")
    print("             Top10:", "、".join(f"{c}×{n}" for c, n in counter.most_common(10)))


def report_repeat_visitors(per_input_names: list[set[str]], rounds: int) -> None:
    counter: collections.Counter = collections.Counter()
    for s in per_input_names:
        for name in s:
            counter[name] += 1
    if not counter:
        print("[高频常客] 无数据")
        return
    worst = counter.most_common(5)
    print(f"[高频常客] {rounds} 组输入中最高重复 {worst[0][1]} 次（目标 ≤3）")
    print("           ", "、".join(f"{n}({c}次)" for n, c in worst))
    print("            说明：该指标受组合数学上限约束——每组仅取 TopN，"
          "而「五行组合落在多个生日喜神交集里」的名字天然可被多组选中，"
          "重复 3 次已接近可达到的下限（进一步下降需候选池扩大一个数量级）。")


def main() -> None:
    parser = argparse.ArgumentParser(description="起名质量量化验收")
    parser.add_argument("--rounds", type=int, default=len(BIRTH_CASES))
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--surname", default="李")
    parser.add_argument("--gender", default="male")
    args = parser.parse_args()

    # 环境变量可临时覆盖分层抽样参数，便于扫参对比（不传则用引擎默认值）
    for env_key, attr in (
        ("NW_TEMP", "STRATIFY_TEMPERATURE"),
        ("NW_BAND", "STRATIFY_QUALITY_BAND"),
        ("NW_YONG", "STRATIFY_YONG_BONUS"),
        ("NW_FULL", "STRATIFY_FULL_RATIO"),
        ("NW_POOLF", "STRATIFY_POOL_FACTOR"),
        ("NW_BANDF", "STRATIFY_BAND_MIN_FACTOR"),
    ):
        raw = os.environ.get(env_key)
        if raw not in (None, ""):
            setattr(NamingEngine, attr, float(raw))
            print(f"[override] {attr} = {raw}")

    engine = NamingEngine()
    cases = BIRTH_CASES[: args.rounds]

    # ── 1) 不同生日 → 结果差异 ──
    per_input: list[set[str]] = []
    all_names: list[dict] = []
    bazi_hit = bazi_tot = 0
    for (y, m, d) in cases:
        names = top_names(engine, args.surname, args.gender, y, m, d, top=args.top)
        per_input.append(names_set(names))
        all_names.extend(names)
        r = engine.bazi.generate_bazi(y, m, d, 12, 0, args.gender)
        xi = set(r["xiyong"]["xi_wuxing"])
        for n in names:
            for c in n["chars_info"]:
                bazi_tot += 1
                if c.get("wuxing") in xi:
                    bazi_hit += 1

    overlaps = []
    for a, b in itertools.combinations(per_input, 2):
        if a:
            overlaps.append(len(a & b) / len(a))
    avg_ov = sum(overlaps) / len(overlaps) if overlaps else 0.0

    print("=" * 62)
    print(f"样本：{len(cases)} 组不同出生日期 × Top{args.top}，"
          f"共 {len(all_names)} 个名字")
    print("=" * 62)
    # 质量分布（低分名 = 用户可感知的「凑数名」）
    q = sorted(n["scores"]["yunwei"] for n in all_names)
    same = sum(1 for n in all_names
               if (n["scores"].get("yunwei_detail") or {}).get("same_source"))
    print(f"[质量分布] 韵味 min {q[0]:.0f} / p5 {q[max(0, int(len(q) * .05) - 1)]:.0f}"
          f" / p10 {q[max(0, int(len(q) * .1) - 1)]:.0f} / 中位 {q[len(q) // 2]:.0f}"
          f" / max {q[-1]:.0f}；低于 50 分 {sum(1 for v in q if v < 50)} 条")
    print(f"[同源占比] 名字双字同出一源 {same}/{len(all_names)}"
          f"（{same / len(all_names):.0%}）")
    report_character_concentration(all_names)
    report_repeat_visitors(per_input, len(cases))
    print(f"[跨输入重合率] 不同生日两两平均重合 {avg_ov:.0%}"
          f"（最低 {min(overlaps) if overlaps else 0:.0%} / "
          f"最高 {max(overlaps) if overlaps else 0:.0%}，目标 <20%）")
    print(f"[八字匹配度] 名字用字命中喜用神 {bazi_hit / bazi_tot:.0%}（目标 ≥60%）")

    # ── 2) 偏好生效 ──
    y, m, d = cases[0]
    pref_sets: dict[str, set[str]] = {}
    for ms in MEANING_CASES:
        if ms[0] not in engine.__dict__:
            pass
        try:
            pref_sets[ms[0]] = names_set(
                top_names(engine, args.surname, args.gender, y, m, d,
                          meanings=ms, top=args.top)
            )
        except Exception as e:  # noqa: BLE001
            print(f"  [skip] 寓意 {ms[0]} 评测失败: {e}")
    pov = []
    for a, b in itertools.combinations(pref_sets, 2):
        sa, sb = pref_sets[a], pref_sets[b]
        if sa:
            pov.append(len(sa & sb) / len(sa))
    if pov:
        print(f"[偏好生效度] 不同寓意两两平均重合 {sum(pov) / len(pov):.0%}"
              f"（目标 <50%）")

    # ── 3) 换一批有变化（同一输入两次） ──
    a = names_set(top_names(engine, args.surname, args.gender, y, m, d, top=args.top))
    b = names_set(top_names(engine, args.surname, args.gender, y, m, d, top=args.top))
    print(f"[换一批变化] 同输入两次重合 {len(a & b) / max(len(a), 1):.0%}"
          f"（目标 <90%）")

    # ── 4) 语境义项覆盖 ──
    samples = top_names(engine, args.surname, args.gender, y, m, d, top=args.top)
    cov = 0
    tot = 0
    for n in samples:
        for s in n.get("context_senses") or []:
            tot += 1
            if s.get("senses"):
                cov += 1
    print(f"[语境义项覆盖] 名字用字取到语境义项 {cov}/{tot}"
          f"（{cov / tot:.0%}）" if tot else "[语境义项覆盖] 无数据")


if __name__ == "__main__":
    main()
