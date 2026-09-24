"""诊断：鹿鸣 这类「动物意象 + 动作」的经典名用词，到底卡在引擎哪一层。

数据层已确认：鹿/鸣 均在字库（均 luck=吉、level 一）；「鹿鸣」在已批准字对
name_pairs.json 里（poem_0002/0079/0156/0168/0174）。故逐层探针找断点。

用法：
    venv/bin/python scripts/diag_luming.py            # 逐层探针 + 小规模抽样
    venv/bin/python scripts/diag_luming.py --sweep 60 # 放大抽样规模
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.constants import NEGATIVE_CHARS  # noqa: E402
from app.services.naming_engine import NamingEngine  # noqa: E402

TARGET_ID_ENTRIES = ["poem_0002", "poem_0079", "poem_0156", "poem_0168", "poem_0174"]
PROBE_CHARS = ["鹿", "鸣", "鹤", "呦", "白"]
TARGET_WORDS = ["鹿鸣", "呦鹿", "鹤鸣", "呦鸣", "白鹿"]


def probe_layers(eng: NamingEngine) -> None:
    print("=" * 68)
    print("[层 1] 字级硬黑名单 NEGATIVE_CHARS")
    for c in PROBE_CHARS:
        print(f"    {c}: {'**被硬黑名单拦截**' if c in NEGATIVE_CHARS else '通过'}")

    print("\n[层 2] 字库收录")
    for c in PROBE_CHARS:
        info = eng.char_db.get_char(c)
        if info:
            print(f"    {c}: 收录 | 五行 {info.get('wuxing')} | luck {info.get('luck')} | "
                  f"meaning={'有' if info.get('meaning') else '**空**'} | "
                  f"imagery={info.get('imagery') or '**空**'}")
        else:
            print(f"    {c}: **未收录**")

    print("\n[层 3] 出处条目是否通过 _match_provenance 的入口条件")
    pairs = json.loads((PROJECT_ROOT / "data/poetry/name_pairs.json").read_text(encoding="utf-8"))
    all_entries = {}
    for gender in ("male", "female"):
        for e in eng.poetry_db.get_by_gender(gender):
            all_entries[e.get("id")] = e
    for eid in TARGET_ID_ENTRIES:
        e = all_entries.get(eid)
        if not e:
            print(f"    {eid}: **不在诗词库 get_by_gender 结果中**")
            continue
        rc = e.get("recommend_chars") or []
        avail = [c for c in rc if eng.char_db.get_char(c) and c not in NEGATIVE_CHARS]
        sad = NamingEngine._is_sad_poem(e)
        print(f"    {eid} | {e.get('source')}·{e.get('title')} | gender={e.get('gender')}")
        print(f"        「{str(e.get('text'))[:36]}」")
        print(f"        recommend_chars={rc}  → 可用 {avail}")
        print(f"        sad_poem={sad}  该条 name_pairs={pairs.get(eid)}")
        print(f"        → {'**被 _is_sad_poem 剔除**' if sad else ('**被可用字为空剔除**' if not avail else '通过入口')}")

    print("\n[层 4] 已批准字对索引 approved_partners")
    for w in TARGET_WORDS:
        owner = None
        try:
            owner = eng.poetry_db.entries_for_pair(w[0], w[1])
        except Exception as exc:  # noqa: BLE001
            owner = f"调用异常: {exc}"
        print(f"    {w}: entries_for_pair → "
              f"{[x.get('id') for x in owner] if isinstance(owner, list) else owner}")


def sweep(eng: NamingEngine, rounds: int) -> None:
    surnames = ["李", "苏", "林", "沈"]
    genders = ["male", "female"]
    dates = [
        (2018, 5, 10), (2020, 8, 20), (2016, 2, 3), (2014, 11, 7),
        (2019, 3, 15), (2017, 7, 22), (2015, 9, 1), (2021, 6, 18),
    ]
    counter: collections.Counter = collections.Counter()
    hits: dict[str, list] = {w: [] for w in TARGET_WORDS}
    n_total = 0
    n_calls = 0

    for surname in surnames:
        for gender in genders:
            for (y, m, d) in dates:
                if n_calls >= rounds:
                    break
                n_calls += 1
                r = eng.generate_names(surname, gender, y, m, d, 12, 0,
                                       name_length=2, max_results=50)
                for n in r["names"]:
                    n_total += 1
                    given = n.get("given_name") or ""
                    counter[given] += 1
                    if given in hits:
                        hits[given].append((surname, gender, f"{y}-{m}-{d}",
                                            n["scores"]["overall"]))
    print("=" * 68)
    print(f"[层 5] 抽样 {n_calls} 次生成，共 {n_total} 个名字，去重 {len(counter)} 个")
    for w in TARGET_WORDS:
        h = hits[w]
        print(f"    {w}: 命中 {len(h)} 次" + (f"  例 {h[0]}" if h else "  （未出现）"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", type=int, default=24, help="抽样生成次数上限")
    args = ap.parse_args()

    eng = NamingEngine()
    probe_layers(eng)
    sweep(eng, args.sweep)


if __name__ == "__main__":
    main()
