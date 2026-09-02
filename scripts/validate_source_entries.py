"""
字源条目校验门禁（T01 / T05 CI Gate）

复用 validate_poetry.py 思路，实现 R1~R8 校验规则。

规则：
R1  recommend_chars 每个字必须 ∈ chars.json 字库
R2  每个推荐字 luck != 凶 且 非负面黑名单
R3  citation 非空且含《…》（格式异常仅警告）
R4  source ∈ {周易,本草纲目,神农本草经,山海经}；source_class = 经史子集
R5  emotion ∈ {喜庆,中性,哀伤}；哀伤条目 recommend_chars 必须为空
R6  category ∈ {中药名,神兽,植物,地名,典籍章句}
R7  imagery 非空（韵味意象分依赖）
R8  id 全局唯一；按 (source,title,text) 去重

用法：
    venv/bin/python scripts/validate_source_entries.py
退出码：无硬错误 → 0；有硬错误 → 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from poetry_utils import PROJECT_ROOT, load_char_map, load_blacklist

DEFAULT_INPUT = PROJECT_ROOT / "data" / "source" / "source_entries.json"

EMOTION_ENUM = {"喜庆", "中性", "哀伤"}
GENDER_ENUM = {"男", "女", "中"}
SOURCE_ENUM = {"周易", "本草纲目", "神农本草经", "山海经"}
SOURCE_CLASS = "经史子集"
CATEGORY_ENUM = {"中药名", "神兽", "植物", "地名", "典籍章句"}


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def validate_entries(entries: list[dict], char_map: dict, blacklist: set) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    seen_ids: set[str] = set()
    seen_keys: set[tuple] = set()

    for e in entries:
        eid = e.get("id", "")
        title = e.get("title", "")
        text = e.get("text", "")
        source = e.get("source", "")
        source_class = e.get("source_class", "")
        category = e.get("category", "")
        emotion = e.get("emotion", "")
        gender = e.get("gender", "")
        citation = e.get("citation", "")
        imagery = e.get("imagery", [])
        recommend_chars = e.get("recommend_chars", [])

        def err(rule: str, msg: str) -> None:
            errors.append({"id": eid, "title": title, "rule": rule, "message": msg})

        def warn(rule: str, msg: str) -> None:
            warnings.append({"id": eid, "title": title, "rule": rule, "message": msg})

        # R8 id 唯一 + 去重
        if not eid:
            err("R8", "缺少 id")
        elif eid in seen_ids:
            err("R8", f"id 重复: {eid}")
        seen_ids.add(eid)
        key = (source, title, text)
        if key in seen_keys:
            err("R8", f"条目重复 (source,title,text): {key}")
        seen_keys.add(key)

        # R4 source/source_class
        if source not in SOURCE_ENUM:
            err("R4", f"source 非法: {source}")
        if source_class != SOURCE_CLASS:
            err("R4", f"source_class 非法: {source_class}（应为 {SOURCE_CLASS}）")

        # R5 emotion
        if emotion not in EMOTION_ENUM:
            err("R5", f"emotion 非法: {emotion}")
        if emotion == "哀伤" and recommend_chars:
            err("R5", f"哀伤条目推荐字非空: {recommend_chars}")

        # R6 category
        if category not in CATEGORY_ENUM:
            warn("R6", f"category 非法: {category}")

        # R3 citation
        if not citation:
            warn("R3", "citation 为空")
        elif "《" not in citation:
            warn("R3", f"citation 格式疑似缺失书名号: {citation}")

        # R7 imagery
        if not imagery:
            warn("R7", "imagery 为空")

        # R1/R2 逐字校验
        for ch in recommend_chars:
            if len(ch) != 1 or not is_cjk(ch):
                err("R1", f"推荐字非法（非单汉字）: {ch!r}")
                continue
            info = char_map.get(ch)
            if not info:
                err("R1", f"推荐字不在字库: {ch}")
                continue
            luck = info.get("luck", "")
            if luck == "凶":
                err("R2", f"推荐字为凶字: {ch}")
            if ch in blacklist:
                err("R2", f"推荐字命中黑名单: {ch}")

    return {"errors": errors, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description="校验字源条目库")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=None, help="校验失败清单输出 JSON 路径")
    args = parser.parse_args()

    path = Path(args.input)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])

    char_map = load_char_map()
    blacklist = load_blacklist()
    report = validate_entries(entries, char_map, blacklist)

    errors = report["errors"]
    warnings = report["warnings"]

    print(f"[validate-source] 共 {len(entries)} 条")
    print(f"  硬错误 {len(errors)} 条，警告 {len(warnings)} 条")

    for e in errors:
        print(f"  [ERROR] {e['rule']} {e['id']}《{e['title']}》{e['message']}")
    for w in warnings:
        print(f"  [WARN ] {w['rule']} {w['id']}《{w['title']}》{w['message']}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    if errors:
        print(f"[validate-source] 校验未通过（{len(errors)} 个硬错误）")
        sys.exit(1)
    print("[validate-source] 校验通过 ✓")


if __name__ == "__main__":
    main()
