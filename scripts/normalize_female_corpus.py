"""
女性向语料扩展：把 chinese-poetry 中「女性气质」材料规范化为 raw_female.jsonl

背景：现有诗词库 499 条中 gender=女 仅 43 条，导致
  ① 女性候选质量差（同源名池 186，男性 242 → 触发质量带宽安全阀）
  ② 女性向诗词本身也是「同源池被源数据硬顶」的根因之一
本脚本只做「规范化（摘句 + 打分 + 预筛）」，不做标注（标注见 llm_annotator.py）。

为什么独立于 normalize_corpus.py：
  标注结果 annotated.jsonl 按 raw id 关联，重跑 normalize_corpus.py 会让 id 整体位移、
  使已有 470 条标注全部错位。故新增材料走独立文件（raw_female.jsonl，id 前缀 fem_），
  再由 merge_poetry.py 增量并入 poetry.json。

新增/扩展来源：
  - 宋词：全宋词（21053 首）中筛「女性词人 + 婉约派代表作者」
  - 五代词：花间集（11 卷）+ 南唐词（李璟/李煜/冯延巳）—— 极度女性向
  - 清词：纳兰性德诗集（258 首）

用法：
    venv/bin/python scripts/normalize_female_corpus.py
    venv/bin/python scripts/normalize_female_corpus.py --out data/poetry/raw_female.jsonl
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from normalize_corpus import (  # noqa: E402
    POSITIVE_KEYWORDS, clean_excerpt, read_json_list, score_excerpt,
    split_excerpts, to_simplified,
)
from poetry_utils import load_blacklist, load_lucky_chars  # noqa: E402

CORPUS_DIR = PROJECT_ROOT / ".corpus"
DEFAULT_OUT = PROJECT_ROOT / "data" / "poetry" / "raw_female.jsonl"

# 每个来源取评分最高的前 quota 条（合计 ≈ 380）
QUOTA = {
    "宋词": 170,      # 全宋词婉约向（在既有「宋词三百首」之外增补）
    "五代词": 150,    # 花间集 + 南唐词
    "清词": 60,       # 纳兰词
}

# 全宋词中的女性词人（据 author 精确匹配）
FEMALE_POETS = {
    "李清照", "朱淑真", "魏夫人", "孙道绚", "严蕊", "唐婉", "吴淑姬",
    "张玉娘", "阮逸女", "花蕊夫人", "王氏", "郑意娘",
}

# 婉约派代表作者（非女性，但词风柔美、意象清丽，适合女性向补充）
WANYUE_POETS = {
    "柳永", "晏几道", "秦观", "周邦彦", "姜夔", "张先", "贺铸",
    "吴文英", "王沂孙", "张炎", "晏殊", "史达祖", "周密", "陈允平",
    "赵长卿", "毛滂", "蔡伸", "陈亮", "高观国", "卢祖皋",
}

# 女性向意象加分词（花/饰/妆/柔美物象）——在原 POSITIVE_KEYWORDS 之上叠加
FEMININE_KEYWORDS = (
    "罗", "绮", "翠", "绣", "香", "鸳", "鸯", "芙", "蓉", "荷", "莲",
    "桃", "柳", "燕", "莺", "黛", "眉", "妆", "裙", "佩", "钗", "环",
    "娟", "娴", "娉", "婷", "娥", "婵", "媛", "姝", "妍", "媚", "绛",
    "素", "纨", "绫", "绡", "珠", "钰", "瑶", "琼", "菱", "薇", "蕙",
)


def feminine_bonus(text: str) -> int:
    """女性向意象加分（每命中一个 +2，上限 +10）。"""
    hits = sum(1 for kw in FEMININE_KEYWORDS if kw in text)
    return min(hits * 2, 10)


def iter_poems(source: str) -> list[dict]:
    """读取指定来源的原始 poem（{title, author, dynasty, paragraphs, provenance}）。"""
    poems: list[dict] = []

    def add(title, author, dynasty, paragraphs, provenance):
        paragraphs = [p for p in paragraphs if p]
        if not paragraphs:
            return
        poems.append({
            "title": to_simplified(title),
            "author": to_simplified(author),
            "dynasty": dynasty,
            "paragraphs": [to_simplified(p) for p in paragraphs],
            "provenance": provenance,
        })

    if source == "宋词":
        files = sorted(glob.glob(str(CORPUS_DIR / "宋词" / "ci.song.[0-9]*.json")))
        for path in files:
            for item in read_json_list(Path(path)):
                author = to_simplified(item.get("author", ""))
                if author not in FEMALE_POETS and author not in WANYUE_POETS:
                    continue
                add(item.get("rhythmic", ""), author, "宋",
                    item.get("paragraphs", []),
                    f"chinese-poetry/宋词/{Path(path).name}")

    elif source == "五代词":
        for path in sorted(glob.glob(str(CORPUS_DIR / "五代诗词" / "huajianji" / "huajianji-*-juan.json"))):
            for item in read_json_list(Path(path)):
                add(item.get("rhythmic") or item.get("title", ""),
                    item.get("author", "佚名"), "唐末",
                    item.get("paragraphs", []),
                    f"chinese-poetry/五代诗词/huajianji/{Path(path).name}")
        nantang = CORPUS_DIR / "五代诗词" / "nantang" / "poetrys.json"
        for item in read_json_list(nantang):
            add(item.get("rhythmic") or item.get("title", ""),
                item.get("author", "佚名"), "五代",
                item.get("paragraphs", []),
                "chinese-poetry/五代诗词/nantang/poetrys.json")

    elif source == "清词":
        path = CORPUS_DIR / "纳兰性德" / "纳兰性德诗集.json"
        for item in read_json_list(path):
            add(item.get("title", ""), item.get("author", "纳兰性德"), "清",
                item.get("para", []), "chinese-poetry/纳兰性德/纳兰性德诗集.json")

    return poems


def build_citation(source: str, title: str) -> str:
    return f"《{title}》"


def normalize() -> list[dict]:
    lucky = load_lucky_chars()
    blacklist = load_blacklist()
    candidates: list[dict] = []
    seen_text: set[str] = set()

    for source in ("宋词", "五代词", "清词"):
        poems = iter_poems(source)
        scored: list[tuple[int, dict]] = []
        for poem in poems:
            original_text = "".join(poem["paragraphs"])
            for excerpt in split_excerpts(poem["paragraphs"]):
                score = score_excerpt(excerpt, lucky, blacklist)
                if score < 0:
                    continue
                score += feminine_bonus(excerpt)
                key = f"{source}|{poem['title']}|{excerpt}"
                if key in seen_text:
                    continue
                seen_text.add(key)
                scored.append((score, {
                    "source": source,
                    "title": poem["title"],
                    "author": poem["author"],
                    "dynasty": poem["dynasty"],
                    "text": excerpt,
                    "original_text": original_text if len(original_text) <= 200
                    else original_text[:200],
                    "citation": build_citation(source, poem["title"]),
                    "provenance": poem["provenance"],
                }))
        scored.sort(key=lambda x: (-x[0], x[1]["text"]))
        picked = [e for _, e in scored[:QUOTA.get(source, 100)]]
        candidates.extend(picked)
        print(f"[normalize_female] {source}: 原始 {len(poems)} 篇 → "
              f"候选摘句 {len(scored)} → 预筛 {len(picked)} 条")

    for i, entry in enumerate(candidates):
        entry["id"] = f"fem_{i + 1:04d}"
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="规范化女性向语料")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    candidates = normalize()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in candidates:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[normalize_female] 完成，共预筛 {len(candidates)} 条 → {out_path}")


if __name__ == "__main__":
    main()
