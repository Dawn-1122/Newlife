#!/usr/bin/env python3
"""
扩字源：把 char_db 里「有《说文解字》本义但无出处」的常用字，组织成「说文解字」字源条目。

背景：
  主流程候选字有一道硬约束（naming_engine._select_candidate_chars）——
  字必须落在 `_provenance_chars()`（诗词+字源 recommend_chars 并集），
  否则哪怕在 chars.json 里有字义/五行/笔画，也不会被选中。

  实测 char_db 共 6492 字，但 provenance 白名单仅约 606 字；其中 160 个「有《说文解字》
  本义却无出处」的字全是高频起名字（鑫/睿/森/楠/梓/萱/涵/瀚/澜/源/汐/煜/旭/曦/峥/磊/枫…）。

  本脚本把这些字按康熙部首（归一化）分组，生成「说文解字·某部」字源条目，纳入
  source_entries.json 的 recommend_chars，让它们进入 provenance 白名单。

只收「适合作名的高频字」白名单（KEEP_CHARS，人工圈定）——char_db 里带《说文解字》
本义但无出处的字共 144 个（level 一），其中大量是「有本义但不适合起名」的常用字
（染/落/暮/暗/狂/骨/羞/貌/蚕/雎…），故用白名单收窄到有明确部首族、能同部组合的高频字。

用法：
    venv/bin/python scripts/expand_source_shuowen.py --dry-run     # 只预览分组，不写
    venv/bin/python scripts/expand_source_shuowen.py               # 实际写入 source_entries.json
"""

from __future__ import annotations

# 适合作名的高频字白名单（人工圈定，可 review）：按《说文解字》部首族，能同部两两组合。
# 未收的散字（睿/彤/孟/宵/野/致/政/佩/屏/幕/涧/鲜/鹿…）因无部首族、无双字搭档，进池后
# 产能极低，留待后续补 name_pairs 标注时一并处理。
KEEP_CHARS = {
    # 金部
    "鑫", "锐", "锋", "铭", "钰", "钧", "鉴", "铉", "铠", "铮",
    # 木部
    "森", "楠", "楷", "栋", "梓", "榕", "枫",
    # 艹部
    "芸", "萱", "菲", "茗", "茂", "蔚", "萧", "艺",
    # 水部
    "淼", "浩", "瀚", "渊", "澜", "涵", "源", "沁", "淳", "渤", "洛", "洋", "汐", "渝",
    # 火部
    "炎", "焱", "煜", "炜", "炫", "烁", "焕", "烽", "焰",
    # 日部
    "旭", "曦", "昕", "晖",
    # 土部 / 山部 / 石部 / 玉部
    "培", "垣", "坦", "峥", "岩", "岭", "磊", "瑰",
}

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.constants import RADICAL_IMAGERY_FAMILIES

# 康熙部首异体归一化：把常见异体归到主部首，保证「艹/艸」「水/氵」等归入同一条
RADICAL_ALIAS = {
    "艸": "艹",
    "氵": "水",
    "钅": "金",
    "釒": "金",
    "灬": "火",
    "忄": "心",
    "扌": "手",
    "亻": "人",
    "纟": "糸",
    "糹": "糸",
    "讠": "言",
    "王": "玉",
    "罒": "网",
}

# 部首 → 意象词（imagery 字段，R7 要求非空）。优先取 RADICAL_IMAGERY_FAMILIES 反查。
def _radical_to_imagery(radical: str) -> str:
    for family, rads in RADICAL_IMAGERY_FAMILIES.items():
        if radical in rads or RADICAL_ALIAS.get(radical, radical) in rads:
            return family
    return radical  # 映射不到就填部首名本身（仍非空）


def load_provenance() -> set[str]:
    """现有出处（诗词 + 字源）recommend_chars 并集。"""
    prov: set[str] = set()
    with open(settings.POETRY_DIR / settings.POETRY_DB_FILE, encoding="utf-8") as f:
        poetry = json.load(f)
    for p in poetry.get("poems", []):
        prov.update(p.get("recommend_chars") or [])
    with open(settings.SOURCE_DIR / settings.SOURCE_ENTRIES_FILE, encoding="utf-8") as f:
        src = json.load(f)
    for e in src.get("entries", []):
        prov.update(e.get("recommend_chars") or [])
    return prov


def load_char_db() -> list[dict]:
    with open(settings.DICT_DIR / settings.CHAR_DB_FILE, encoding="utf-8") as f:
        return json.load(f)["chars"]


def build_groups(chars: list[dict], provenance: set[str]) -> OrderedDict:
    """找出「白名单内、有 shuowen 本义、无出处」的字，按归一化部首分组。"""
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for c in chars:
        ch = c["char"]
        if ch in provenance or ch not in KEEP_CHARS:
            continue
        if not (c.get("shuowen") or "").strip():
            continue
        radical = c.get("radical", "?") or "?"
        radical = RADICAL_ALIAS.get(radical, radical)
        groups.setdefault(radical, []).append(c)
    return groups


def make_entries(groups: OrderedDict, start_id: int) -> list[dict]:
    """把分组转成 source_entries 条目（source=说文解字）。"""
    entries: list[dict] = []
    idx = start_id
    for radical, chars in groups.items():
        # 部首内按常用度（level 已是「一」）保持字库原序即可
        recommend = [c["char"] for c in chars]
        text_parts = []
        for c in chars:
            sw = (c.get("shuowen") or "").strip()
            if sw:
                text_parts.append(f"{c['char']}：{sw}")
        entries.append({
            "id": f"src_{idx:04d}",
            "source": "说文解字",
            "source_class": "经史子集",
            "category": "字源",
            "title": f"{radical}部",
            "author": "许慎",
            "dynasty": "东汉",
            "text": "。".join(text_parts),
            "original_text": None,
            "citation": f"《说文解字·{radical}部》",
            "recommend_chars": recommend,
            "emotion": "中性",
            "imagery": [_radical_to_imagery(radical)],
            "gender": "中",
            "scene": "",
            "tags": ["字源", "说文解字"],
            "provenance": "",
        })
        idx += 1
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只预览分组，不写文件")
    args = parser.parse_args()

    chars = load_char_db()
    provenance = load_provenance()
    groups = build_groups(chars, provenance)

    total_chars = sum(len(v) for v in groups.values())
    print(f"[expand] 待扩字源：{total_chars} 字，{len(groups)} 个部首分组")
    for radical, g in groups.items():
        chars_str = "".join(c["char"] for c in g)
        print(f"  {radical}部 ({len(g)}): {chars_str}")

    if args.dry_run:
        print("[expand] --dry-run，未写入")
        return 0

    # 幂等：先移除已有「说文解字」条目，再追加新条目
    src_path = settings.SOURCE_DIR / settings.SOURCE_ENTRIES_FILE
    with open(src_path, encoding="utf-8") as f:
        data = json.load(f)

    existing = [e for e in data["entries"] if e.get("source") != "说文解字"]
    max_id = 0
    for e in existing:
        m = e.get("id", "")
        if m.startswith("src_") and m[4:].isdigit():
            max_id = max(max_id, int(m[4:]))
    new_entries = make_entries(groups, start_id=max_id + 1)
    data["entries"] = existing + new_entries
    data["total"] = len(data["entries"])

    with open(src_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[expand] 写入 {len(new_entries)} 条「说文解字」字源条目，"
          f"source_entries 现共 {data['total']} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
