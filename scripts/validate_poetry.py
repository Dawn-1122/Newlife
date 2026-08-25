"""
T4 · 交叉校验（入库前置 Gate）

实现 R1~R11 校验规则，作为 poetry.json 合入前的质量门禁。

规则：
R1  recommend_chars 每个字必须 ∈ chars.json 字库
R2  每个推荐字 luck == 吉（「凶」→ 硬错误；「中」→ 警告，按设计需人工复核，不硬删）
R3  负面字黑名单（字库 luck=凶 ∪ blacklist.json）
R4  emotion ∈ {喜庆, 中性, 哀伤}
R5  emotion==哀伤 时 recommend_chars 必须为空
R6  gender ∈ {男, 女, 中}
R7  source ∈ 6 大类
R8  citation 非空且含《…》（格式异常仅警告）
R9  text 非空且 2~30 字
R10 id 全局唯一
R11 条目去重：按 (source,title,text) 及 recommend_chars 组合

用法：
    venv/bin/python scripts/validate_poetry.py --input data/poetry/poetry.json
退出码：无硬错误 → 0；有硬错误 → 1（CI Gate）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from poetry_utils import PROJECT_ROOT, load_char_map, load_blacklist

DEFAULT_INPUT = PROJECT_ROOT / "data" / "poetry" / "poetry.json"

EMOTION_ENUM = {"喜庆", "中性", "哀伤"}
GENDER_ENUM = {"男", "女", "中"}
SOURCE_ENUM = {"诗经", "楚辞", "唐诗", "宋词", "汉魏古诗", "经史子集"}


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def text_len(text: str) -> int:
    return sum(1 for ch in text if is_cjk(ch))


def validate_poems(poems: list[dict], char_map: dict, blacklist: set) -> dict:
    """校验全部诗词，返回 {errors, warnings}。"""
    errors: list[dict] = []
    warnings: list[dict] = []

    seen_ids: set[str] = set()
    seen_keys: set[tuple] = set()
    seen_char_combos: set[tuple] = set()

    for p in poems:
        pid = p.get("id", "")
        title = p.get("title", "")
        text = p.get("text", "")
        source = p.get("source", "")
        emotion = p.get("emotion", "")
        gender = p.get("gender", "")
        citation = p.get("citation", "")
        recommend_chars = p.get("recommend_chars", [])

        def err(rule: str, msg: str) -> None:
            errors.append({"id": pid, "title": title, "rule": rule, "message": msg})

        def warn(rule: str, msg: str) -> None:
            warnings.append({"id": pid, "title": title, "rule": rule, "message": msg})

        # R10 id 唯一
        if not pid:
            err("R10", "缺少 id")
        elif pid in seen_ids:
            err("R10", f"id 重复: {pid}")
        seen_ids.add(pid)

        # R7 source 枚举
        if source not in SOURCE_ENUM:
            err("R7", f"source 非法: {source}")

        # R4 emotion 枚举
        if emotion not in EMOTION_ENUM:
            err("R4", f"emotion 非法: {emotion}")

        # R6 gender 枚举
        if gender not in GENDER_ENUM:
            err("R6", f"gender 非法: {gender}")

        # R8 citation 非空 + 格式
        if not citation:
            warn("R8", "citation 为空")
        elif "《" not in citation:
            warn("R8", f"citation 格式疑似缺失书名号: {citation}")

        # R9 text 长度
        n = text_len(text or "")
        if not text:
            err("R9", "text 为空")
        elif not (2 <= n <= 30):
            err("R9", f"text 长度 {n} 不在 2~30 之间")

        # R5 哀伤 → 推荐字为空
        if emotion == "哀伤" and recommend_chars:
            err("R5", f"哀伤条目推荐字非空: {recommend_chars}")

        # R1/R2/R3 逐字校验
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
            elif luck != "吉":
                warn("R2", f"推荐字非吉（{luck}）: {ch}，待人工复核")
            if ch in blacklist:
                err("R3", f"推荐字命中黑名单: {ch}")

        # R11 去重
        key = (source, title, text)
        if key in seen_keys:
            err("R11", f"条目重复 (source,title,text): {key}")
        seen_keys.add(key)

        combo = tuple(sorted(recommend_chars))
        if combo and combo in seen_char_combos:
            warn("R11", f"推荐字组合重复: {combo}")
        if combo:
            seen_char_combos.add(combo)

    return {"errors": errors, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description="校验诗词库")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=None, help="校验失败清单输出 JSON 路径")
    args = parser.parse_args()

    path = Path(args.input)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    poems = data.get("poems", [])

    char_map = load_char_map()
    blacklist = load_blacklist()
    report = validate_poems(poems, char_map, blacklist)

    errors = report["errors"]
    warnings = report["warnings"]

    print(f"[validate] 共 {len(poems)} 首")
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
        print(f"[validate] 校验未通过（{len(errors)} 个硬错误）")
        sys.exit(1)
    print("[validate] 校验通过 ✓")


if __name__ == "__main__":
    main()
