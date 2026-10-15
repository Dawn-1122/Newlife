#!/usr/bin/env python
"""
先字模式（selected_chars = 名字必须含所选字）覆盖诊断。

背景：先字模式的产能 = 「所选字在已批准字对（name_pairs）里的搭档数」。
语料标注量决定供给上限——单个字可能是 20+ 个名字，也可能 0 个。
前端「先字」字表必须按本脚本的覆盖表给出（只列有覆盖的字），
否则用户点到 0 覆盖的字会拿到空结果，体感「系统坏了」。

用法：
    # ① 结构覆盖表（默认，不跑引擎，秒出）：每性别「池内字 → 可组搭档数」分布
    venv/bin/python scripts/diag_selected_chars.py

    # ② 单字细察：列出该字全部可用搭档 + 所在出处
    venv/bin/python scripts/diag_selected_chars.py --char 清 --gender female

    # ③ live 验证：真实跑 generate_names，逐字报告实际产出（含门槛损耗）
    venv/bin/python scripts/diag_selected_chars.py --live 清,月,秋,竹 --surname 林 --gender female

    # ④ 导出可选字表（供前端「先字」网格）
    venv/bin/python scripts/diag_selected_chars.py --export data/poetry/pickable_chars.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.naming_engine import NamingEngine
from app.core.constants import NEGATIVE_CHARS


def build_coverage(engine: NamingEngine, gender: str) -> dict:
    """结构覆盖表：池内每个字 → 可组搭档（字数 + 明细）。

    口径与引擎一致：
    - 池 = _select_candidate_chars（出处白名单 + 性别 + 非黑名单）
    - 已标注出处：只认 name_pairs 中含该字的字对（搭档也须在池内）
    - 未标注出处（name_pairs_known=False）：全交叉兜底——该字与同条出处其余可用字
    - 出处须性别可见 + 非哀伤（与 _match_provenance 一致）
    """
    blacklist = set(NEGATIVE_CHARS)
    pool = {c["char"] for c in engine._select_candidate_chars(
        None, gender, 2, blacklist, None
    )}

    coverage: dict[str, dict[str, set]] = {
        ch: {"partners": set(), "entries": set()} for ch in pool
    }

    for entry in engine.poetry_db.get_by_gender(gender):
        if engine._is_sad_poem(entry):
            continue
        usable = [
            c for c in (entry.get("recommend_chars") or [])
            if c in pool
        ]
        usable_set = set(usable)
        pairs = entry.get("name_pairs") or []
        known = entry.get("name_pairs_known", bool(pairs))
        title = f'{entry["source"]}·{entry["title"]}'

        if pairs:
            for a, b in pairs:
                if a not in pool or b not in pool:
                    continue
                coverage[a]["partners"].add(b)
                coverage[b]["partners"].add(a)
                coverage[a]["entries"].add(title)
                coverage[b]["entries"].add(title)
        elif not known:
            # 未标注出处：全交叉（引擎同款兜底路径）
            for a in usable:
                for b in usable:
                    if a == b:
                        continue
                    coverage[a]["partners"].add(b)
                    coverage[a]["entries"].add(title)

    # 只保留池内字
    return {ch: v for ch, v in coverage.items() if ch in pool}


def print_summary(coverage: dict, gender: str) -> None:
    buckets = [0, 1, 3, 6, 11, 21, 999]
    labels = ["0（不可选）", "1-2", "3-5", "6-10", "11-20", "21+"]
    dist = [0] * (len(buckets) - 1)
    for v in coverage.values():
        n = len(v["partners"])
        for i in range(len(buckets) - 1):
            if buckets[i] <= n < buckets[i + 1]:
                dist[i] += 1
                break
    print(f"\n===== {gender} · 池内字 {len(coverage)} 个 · 搭档数分布 =====")
    for label, cnt in zip(labels, dist):
        print(f"  {label:>12}: {cnt}")

    ranked = sorted(coverage.items(), key=lambda kv: -len(kv[1]["partners"]))
    print("  覆盖最厚 20 字:", " ".join(
        f"{ch}({len(v['partners'])})" for ch, v in ranked[:20]
    ))
    zeros = [ch for ch, v in coverage.items() if not v["partners"]]
    print(f"  零覆盖（先字字表须排除）: {len(zeros)} 字")
    if zeros:
        print("   ", " ".join(zeros[:60]))


def build_feasibility(engine: NamingEngine, surname: str, gender: str,
                      source_classes: list | None = None) -> dict:
    """门槛感知可行性：这个字和这个姓氏，能不能真的出名字。

    结构覆盖（build_coverage）只是上界——实际还有一道门槛层会拦下大量组合，
    且**与姓氏强相关**：如姓「林」（阳平）时，名字两字全平触发三连同调全灭
    （清扬/芙蓉/芳兰）；「林」+「诗」谐音「临时」被谐音禁则拦下。

    本函数镜像引擎的**两条供给路径**，只跑门槛层、不做韵味评分/抽样：
    A. 出处组合路径（compose_from_entry）：出处须过 _match_provenance 的可用性过滤；
       有标注出处只产标注字对（字序按原文），未标注出处全交叉。
    B. 随机组合路径：搭档 =「已批准字对 ∩ 候选池」（出处仅作挂载，不参与）。
    两条路径任一能产出名字即视为可行。与 live 对拍（244 字）零偏差为验收标准。
    """
    blacklist = set(NEGATIVE_CHARS)
    pool = {c["char"]: c for c in engine._select_candidate_chars(
        None, gender, 2, blacklist, None
    )}
    hits: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)

    def gate_ok(first: dict, second: dict):
        """过门槛层（三连同调 + 音律 + 五格 + 姓氏谐音/本义）→ 返回名字，否则 None。"""
        gn = first["char"] + second["char"]
        if engine.surname_fit.tri_tone_conflict(
            surname, [first["char"], second["char"]]
        ):
            return None
        ph = engine.phonetics.analyze(surname + gn)
        try:
            wg = engine.wuge.calculate(surname, gn)
        except Exception:
            wg = {"total_score": 60}
        if not engine._pass_gate(surname, gn, ph, wg, None, [first, second]):
            return None
        return gn

    def record(a: str, b: str, gn: str) -> None:
        for ch in (a, b):
            if gn not in seen[ch]:
                seen[ch].add(gn)
                hits[ch].append(gn)

    # ── 供给 A：出处组合路径 ──
    for entry, _tier in engine._match_provenance(
        None, gender, None, None, blacklist, source_classes=source_classes
    ):
        by_char = {
            c["char"]: c for c in
            engine._get_valid_poem_chars(entry, gender, None, blacklist, None)
        }
        for pair in (entry.get("name_pairs") or []):
            for ch in pair:
                if ch in by_char or ch in blacklist:
                    continue
                ci = engine.char_db.get_char(ch)
                if not ci:
                    continue
                if gender == "male" and ci["gender"] not in ("男", "中"):
                    continue
                if gender == "female" and ci["gender"] not in ("女", "中"):
                    continue
                by_char[ch] = ci
        annotated = entry.get("name_pairs") or []
        known = entry.get("name_pairs_known", bool(annotated))
        if annotated:
            pair_list = [tuple(p) for p in annotated if all(ch in by_char for ch in p)]
        elif known:
            pair_list = []
        else:
            chars = list(by_char)
            pair_list = [
                (a, b) for i, a in enumerate(chars) for b in chars[i + 1:]
            ]
        for a, b in pair_list:
            first, second = engine._order_two_chars(entry, by_char[a], by_char[b])
            gn = gate_ok(first, second)
            if gn:
                record(a, b, gn)

    # ── 供给 B：随机组合路径（搭档 = 已批准字对 ∩ 候选池；音韵定序，同分两序均为候选）──
    for ch, ci in pool.items():
        for p in set(engine.poetry_db.approved_partners(ch)):
            if p == ch or p not in pool:
                continue
            for first, second in engine._order_candidates(ci, pool[p]):
                gn = gate_ok(first, second)
                if gn:
                    record(ch, p, gn)
                    break

    return {
        ch: {
            "partners": len(set(engine.poetry_db.approved_partners(ch)) & set(pool)),
            "name_hits": len(hits[ch]),
            "sample": sorted(hits[ch])[:8],
        }
        for ch in pool
        if hits[ch] or set(engine.poetry_db.approved_partners(ch)) & set(pool)
    }


def print_feasibility(feas: dict, surname: str, gender: str) -> None:
    ok = {ch: v for ch, v in feas.items() if v["name_hits"]}
    print(f"\n===== {surname}姓 / {gender} · 门槛感知可行性 =====")
    print(f"  池内有字对的字 {len(feas)} 个 → 实际出得来名字 {len(ok)} 个")
    ranked = sorted(ok.items(), key=lambda kv: -kv[1]["name_hits"])
    print("  最可行 20 字:", " ".join(f"{ch}({v['name_hits']})" for ch, v in ranked[:20]))
    dead = sorted(ch for ch, v in feas.items() if not v["name_hits"])
    print(f"  有字对但门槛全灭: {len(dead)} 字")
    if dead:
        print("   ", " ".join(dead))


def show_char(engine: NamingEngine, char: str, gender: str, coverage: dict) -> None:
    v = coverage.get(char)
    if not v:
        print(f"「{char}」不在 {gender} 池内（出处白名单/性别/黑名单之外），先字模式产不出名字。")
        return
    partners = sorted(v["partners"], key=lambda p: -len(coverage.get(p, {}).get("partners", set())))
    print(f"\n「{char}」（{gender}）可用搭档 {len(partners)} 个：")
    print("  ", " ".join(partners))
    print(f"  所在出处 {len(v['entries'])} 条：")
    for t in sorted(v["entries"])[:15]:
        print("   -", t)


def run_live(engine: NamingEngine, chars: list[str], surname: str, gender: str) -> None:
    print(f"\n===== live 验证（姓 {surname} / {gender}）=====")
    print(f"{'字':<3}{'搭档':>5}{'产出':>5}  名字")
    for ch in chars:
        result = engine.generate_names(
            surname=surname, gender=gender, name_length=2, max_results=30,
            selected_chars=[ch],
        )
        names = [n["given_name"] for n in result["names"]]
        violated = [n for n in names if ch not in n]
        flag = "" if not violated else f"  ⚠️违约:{violated}"
        print(f"{ch:<3}{'':>5}{result['total']:>5}  {' '.join(names[:14])}{flag}")
        if result["fallback_note"]:
            print(f"      note: {result['fallback_note']}")


def main():
    parser = argparse.ArgumentParser(description="先字模式覆盖诊断")
    parser.add_argument("--char", help="细察单个字")
    parser.add_argument("--gender", default="female", choices=["male", "female"])
    parser.add_argument("--live", help="live 验证，逗号分隔字列表")
    parser.add_argument("--surname", default="林")
    parser.add_argument("--feasible", action="store_true",
                        help="门槛感知可行性：该姓氏下真正出得来名字的字（与姓氏强相关）")
    parser.add_argument("--export", help="导出可选字表 JSON 路径")
    args = parser.parse_args()

    engine = NamingEngine()
    coverage = build_coverage(engine, args.gender)
    print_summary(coverage, args.gender)

    if args.feasible:
        import time
        t0 = time.time()
        feas = build_feasibility(engine, args.surname, args.gender)
        print_feasibility(feas, args.surname, args.gender)
        print(f"  （可行性计算用时 {time.time() - t0:.2f}s）")

    if args.char:
        show_char(engine, args.char, args.gender, coverage)
    if args.live:
        run_live(engine, [c for c in args.live.replace("，", ",").split(",") if c],
                 args.surname, args.gender)
    if args.export:
        payload = {
            "gender": args.gender,
            "chars": {
                ch: {
                    "partners": sorted(v["partners"]),
                    "partner_count": len(v["partners"]),
                }
                for ch, v in sorted(coverage.items(), key=lambda kv: -len(kv[1]["partners"]))
            },
        }
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n可选字表已导出：{out}（{len(payload['chars'])} 字）")


if __name__ == "__main__":
    main()
