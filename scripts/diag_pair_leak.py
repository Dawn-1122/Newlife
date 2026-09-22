"""诊断「同源名两字」的语义层漏网情况（可复用）。

对多组输入生成名字，把每个同源双字名按**成因**归类：

| 成因 | 含义 | 处置 |
|---|---|---|
| `in_annotation` | 该字对在 name_pairs 标注内 | ✅ 正常 |
| `annotation_empty` | 出处已标注但字对全被复核剔除 → 退回全交叉 | ⚠️ 漏网主因，应禁止退回 |
| `no_annotation` | 出处根本没跑过标注 → 退回全交叉 | ⚠️ 覆盖洞 |
| `not_paired` | 有标注但产出不在标注内 | ❌ 引擎 bug |

用法：
    ./venv/bin/python scripts/diag_pair_leak.py [--top 40] [--show 12]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.naming_engine import NamingEngine  # noqa: E402

CASES = [
    ("苏", "female", 2020, 8, 20),
    ("林", "female", 2019, 3, 12),
    ("陈", "male", 2018, 11, 5),
    ("周", "male", 2021, 6, 1),
    ("李", "female", 2022, 2, 14),
    ("王", "male", 2017, 9, 9),
]


def load_annotation() -> dict[str, list]:
    path = settings.POETRY_DIR / "name_pairs.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40, help="每组取前 N 名")
    ap.add_argument("--show", type=int, default=12, help="每组打印前 N 名")
    args = ap.parse_args()

    annotation = load_annotation()
    engine = NamingEngine()
    poems = engine.poetry_db._poems
    by_text = {(p.get("text") or "").strip(): p for p in poems if p.get("text")}

    tally: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)

    for sn, g, y, m, d in CASES:
        res = engine.generate_names(
            surname=sn, gender=g, name_length=2,
            year=y, month=m, day=d, max_results=args.top,
        )
        heads = [n["given_name"] for n in res["names"][: args.show]]
        print(f"\n{sn} {g} {y}-{m:02d}-{d:02d}  →  " + " / ".join(heads))

        for n in res["names"]:
            det = n["scores"]["yunwei_detail"]
            if not det.get("same_source"):
                continue
            given = n["given_name"]
            # 用结果里自带的出处原文精确反查（比「首条覆盖两字的出处」可靠）
            entry = by_text.get((n.get("poetry") or {}).get("text", "").strip())
            if entry is None:
                tally["unresolved"] += 1
                samples["unresolved"].append(given)
                continue

            eid = entry["id"]
            pairs = ["".join(x) for x in (entry.get("name_pairs") or [])]
            pair_key = given if given in pairs else (given[::-1] if given[::-1] in pairs else None)

            if pair_key:
                tally["in_annotation"] += 1
            elif pairs:
                tally["not_paired"] += 1
                samples["not_paired"].append(f"{given}@{eid}")
            elif eid in annotation:
                tally["annotation_empty"] += 1
                samples["annotation_empty"].append(f"{given}@{eid}")
            else:
                tally["no_annotation"] += 1
                samples["no_annotation"].append(f"{given}@{eid}")

    total = sum(tally.values())
    print("\n" + "=" * 62)
    print(f"共诊断 {total} 个同源双字名")
    for k in ("in_annotation", "annotation_empty", "no_annotation", "not_paired", "unresolved"):
        v = tally.get(k, 0)
        pct = f"{v / total * 100:5.1f}%" if total else "  n/a"
        print(f"  {k:18s} {v:4d}  {pct}   {[s for s in samples[k][:8]]}")

    # 未标注出处的规模
    all_ids = {p["id"] for p in poems if p.get("recommend_chars")}
    annotated = {i for i, v in annotation.items() if v}
    empty = {i for i, v in annotation.items() if not v}
    never = all_ids - set(annotation)
    print("\n出处标注覆盖：")
    print(f"  有字对 {len(annotated)} / 标注命中但空 {len(empty)} / 从未标注 {len(never)}")
    print(f"  有推荐字的出处共 {len(all_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
