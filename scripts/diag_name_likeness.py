"""名字「组合成立度」诊断：名字的两字在出处原文里到底是什么关系。

背景（用户反馈）：同源名是把一条出处的推荐字做**全交叉组合**取两个出来，
没有任何「这两个字合起来像不像名字」的判断 —— 于是会出现
「苏红黄」「苏萸橘」（颜色/草木名堆叠）、「苏赦伐」（动+动）这类
「只是从同一句里抠了俩字」的结果。

本脚本把「两字在原文中的关系」作为「组合成立度」的可观测代理指标：

    相邻      两字在原文里连着出现（如「婵娟」「嘉宾」）—— 最强信号，本就是词
    同句      在同一分句内但不相邻（如「灼…其华」）—— 尚可
    跨句      分处两个分句（如「嘉…鼓瑟吹笙」）—— 机械拼接
    字不在原文 推荐字没出现在原文里 —— 靠意象标签推的，最弱

用法：
    venv/bin/python scripts/diag_name_likeness.py                 # 默认 18 组 × Top30
    venv/bin/python scripts/diag_name_likeness.py --rounds 6 --top 20
    venv/bin/python scripts/diag_name_likeness.py --samples       # 打印各类样例
"""

from __future__ import annotations

import argparse
import collections
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.naming_engine import NamingEngine  # noqa: E402
from app.services.yunwei_scorer import pair_cohesion  # noqa: E402

BIRTH_CASES = [
    (2018, 5, 10), (2020, 8, 20), (2016, 2, 3), (2014, 11, 7),
    (2019, 3, 15), (2017, 7, 22), (2015, 9, 1), (2021, 6, 18),
    (2013, 4, 25), (2022, 1, 12), (2012, 10, 5), (2011, 12, 30),
    (2010, 8, 8), (2009, 5, 19), (2008, 3, 3), (2007, 11, 11),
    (2006, 2, 14), (2005, 6, 6),
]

# 引擎内部 kind -> 中文标签（单一事实源：pair_cohesion）
_KIND_LABEL = {
    "adjacent": "相邻",
    "same_clause": "同句",
    "cross_clause": "跨句",
    "char_absent": "字不在原文",
}

REL_ORDER = ["相邻", "同句", "跨句", "字不在原文", "无出处", "单字名"]


def relation_of(text: str, a: str, b: str) -> str:
    """两字在原文中的关系（复用引擎口径，保证与打分/排序一致）。"""
    return _KIND_LABEL[pair_cohesion(a, b, text)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=len(BIRTH_CASES))
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--samples", action="store_true", help="打印各类样例名字")
    args = ap.parse_args()

    # 给结果挂上出处 id / 性别，便于回查（不改引擎行为）
    original = NamingEngine._evaluate_name

    def patched(self, surname, given_name, chars_info, entry=None, bazi_result=None):
        result = original(self, surname, given_name, chars_info, entry, bazi_result)
        if isinstance(result, dict) and entry:
            result["_eid"] = entry.get("id")
            result["_text"] = entry.get("text") or ""
        return result

    NamingEngine._evaluate_name = patched  # type: ignore[method-assign]

    engine = NamingEngine()
    counter: collections.Counter = collections.Counter()
    samples: dict[str, list[str]] = collections.defaultdict(list)
    yunwei: dict[str, list[int]] = collections.defaultdict(list)
    total = 0

    for (year, month, day) in BIRTH_CASES[: args.rounds]:
        for gender in ("male", "female"):
            res = engine.generate_names(
                "苏", gender, year, month, day, 12, 0,
                name_length=2, max_results=args.top,
            )
            for name in res["names"]:
                given = name["given_name"]
                text = name.get("_text") or ""
                if len(given) < 2:
                    rel = "单字名"
                elif not text and not name.get("_eid"):
                    rel = "无出处"
                else:
                    rel = relation_of(text, given[0], given[1])
                counter[rel] += 1
                total += 1
                yunwei[rel].append(name["scores"]["yunwei"])
                if len(samples[rel]) < 12:
                    samples[rel].append(
                        f"{name['full_name']}({name['scores']['yunwei']})"
                        f"《{(name.get('poetry') or {}).get('title', '')}》"
                    )

    NamingEngine._evaluate_name = original  # type: ignore[method-assign]

    print("=" * 66)
    print(f"样本：{args.rounds} 组生日 × 男女 × Top{args.top}，共 {total} 个名字")
    print("=" * 66)
    print("[两字与原文的关系分布]")
    for rel in REL_ORDER:
        n = counter.get(rel, 0)
        if not n:
            continue
        scores = yunwei[rel]
        bar = "█" * max(1, round(n / total * 40))
        print(
            f"  {rel:<6} {n:>4} ({n / total * 100:>5.1f}%) {bar}"
            f"  韵味 min={min(scores)} 中位={int(statistics.median(scores))}"
        )

    mechanical = counter.get("跨句", 0) + counter.get("字不在原文", 0)
    print()
    print(f"[机械拼接占比] 跨句 + 字不在原文 = {mechanical}/{total} "
          f"（{mechanical / total * 100:.1f}%）—— 这就是「只是抠了两个字」的部分")

    if args.samples:
        print()
        for rel in REL_ORDER:
            if samples.get(rel):
                print(f"[{rel}] 样例：")
                for s in samples[rel][:12]:
                    print(f"    {s}")
                print()


if __name__ == "__main__":
    main()
