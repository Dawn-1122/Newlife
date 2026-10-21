"""「名字感」评审：抽样导出 + 评分回写

背景：
`name_pairs.json` 的 814 个字对是「诗句里宜作名的两字组合」，
判据来自 `pair_annotator.py` + `pair_review.py` 两道 LLM 闸。但那两道闸的取向是
**古典雅正**，`pair_review.py` 甚至把「银河/雪海/青天/暗香/花月/秋风/秋菊/芦花」
写进保护名单——正是当代用户觉得「土」的那一批。于是产出的是「诗句里的好词」，
不是「当代人的名字」。

本脚本补第三道闸：**名字感评分（1~5）**，判据是「愿不愿意写在出生证明上」，
不是「像不像诗里的好词」。评分以外部 JSON 形式落盘，可审、可回退、可分批。

用法：
    venv/bin/python scripts/pair_taste.py --sample 60      # 分层抽样导出待评表
    venv/bin/python scripts/pair_taste.py --apply FILE     # 按评分文件过滤字对

评分文件格式（--apply 的输入）：
    {"望舒": 5, "静姝": 5, "春风": 1, ...}     # 缺省视为 4（不删）
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

PAIRS = PROJECT_ROOT / "data" / "poetry" / "name_pairs.json"
POEMS = PROJECT_ROOT / "data" / "poetry" / "poetry.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "poetry" / "pair_taste_sample.md"

# 时代感强的民间吉祥 / 器物用字：作实义时最土（翠凤、瑞祥、水生、宝兴）
FOLK = set("翠凤银珠瑞祥彩霞金宝财富贵福禄寿喜旺发荣桂娥娟淑贤惠生秀英芳兰玉梅红绿香花")
# 自然景物字：字本身雅，但两字直取成词（春风/银河/雪海）就土
SCENERY = set("月风雪花云水山天光星日江河海雨露霜烟霞阳晴暖寒清碧苍素皓白青绿红紫")


def load_pairs() -> dict[str, list[list[str]]]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def load_poems() -> dict[str, dict]:
    data = json.loads(POEMS.read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["poems"]}


def flatten(pairs: dict[str, list[list[str]]]) -> list[tuple[str, str]]:
    """(字对, entry_id) 列表。"""
    out = []
    for eid, ps in pairs.items():
        for p in ps:
            if isinstance(p, list) and len(p) == 2:
                out.append((p[0] + p[1], eid))
    return out


def sample(rows: list[tuple[str, str]], n: int, seed: int = 20261021) -> list[tuple[str, str]]:
    """分层抽样：俗字组 / 景物组 / 其余，各占 1/3，保证样张覆盖各种土法。"""
    rnd = random.Random(seed)
    folk = [r for r in rows if any(c in FOLK for c in r[0])]
    scen = [r for r in rows if r not in folk and any(c in SCENERY for c in r[0])]
    rest = [r for r in rows if r not in folk and r not in scen]
    per = n // 3
    picked: list[tuple[str, str]] = []
    for group in (folk, scen, rest):
        rnd.shuffle(group)
        picked.extend(group[:per])
    remain = n - len(picked)
    if remain > 0:
        pool = [r for r in rows if r not in picked]
        rnd.shuffle(pool)
        picked.extend(pool[:remain])
    picked.sort(key=lambda r: (r[0] not in folk, r[1]))
    return picked


def write_markdown(picked, poems, out: Path) -> None:
    lines = [
        "# 名字感评审 · 分层样张",
        "",
        "判据：**愿不愿意写在出生证明上**（不是「像不像诗里的好词」）。",
        "",
        "| # | 字对 | 出处 | 原文 | 评分 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i, (word, eid) in enumerate(picked, 1):
        p = poems.get(eid, {})
        cite = p.get("citation") or p.get("title") or eid
        text = (p.get("text") or "").replace("|", "／")
        if len(text) > 42:
            text = text[:42] + "…"
        lines.append(f"| {i} | {word} | {cite} | {text} |  |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def do_sample(n: int, out: Path) -> None:
    rows = flatten(load_pairs())
    picked = sample(rows, n)
    write_markdown(picked, load_poems(), out)
    print(f"[taste] 全量字对 {len(rows)} 个，导出 {len(picked)} 条 → {out}")
    print("[taste] 评分 1=土/怪/不宜作名  3=勉强  4=可以  5=好名字")


def do_apply(score_file: Path, min_score: int) -> None:
    scores: dict[str, int] = json.loads(score_file.read_text(encoding="utf-8"))
    data = load_pairs()
    removed, kept_pairs = 0, 0
    kept: dict[str, list[list[str]]] = {}
    for eid, ps in data.items():
        survive = []
        for p in ps:
            if not (isinstance(p, list) and len(p) == 2):
                continue
            word = p[0] + p[1]
            if scores.get(word, 4) < min_score:
                removed += 1
            else:
                survive.append(p)
        kept[eid] = survive
        kept_pairs += len(survive)
    backup = PAIRS.with_suffix(".json.bak")
    backup.write_text(PAIRS.read_text(encoding="utf-8"), encoding="utf-8")
    PAIRS.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[taste] 剔除 {removed} 个字对，剩余 {kept_pairs} 个"
          f"（{sum(1 for v in kept.values() if v)}/{len(kept)} 条出处仍有字对）")
    print(f"[taste] 原文件已备份到 {backup.name}")


# --------------------------------------------------------------------------- #
# 分级（1~5 分）：全量人工审定，**默认屏蔽**
#
# 为什么不再靠规则：「玉/香/红/翠」这类俗字仅占土名的一小部分，更多土法是
# 现成词（春风/明月/冰雪/星河）、具象景物直取（清溪/白露/微雨/月霜）、
# 动宾短语（乘风/如水/珍重/悠扬）、理学术语（明德/博文外的仁义礼智）。这些
# 字面全是好字，字符规则抓不住；而语料只有 671 个字对，逐条判比写规则更准、
# 也更好审。故：白名单外一律 1 分（不出），新增语料未定级时也能被 `--build`
# 的覆盖检查与 tests/test_pair_taste.py 抓到。
#
# 判据只有一条：**愿不愿意写在出生证明上**（不是「像不像诗里的好词」）。
# --------------------------------------------------------------------------- #

# 5 分：当代愿写进出生证明，有典、不直白指物
TOP = {
    "静姝", "灼华", "鹤鸣", "鹿鸣", "清扬", "婉清", "静嘉", "乔松", "柔嘉",
    "如琢", "修远", "婵娟", "素秋", "嘉树", "疏影", "子思", "致远",
}

# 4 分：可用，略书面或略生僻，但不是日常词
GOOD = {
    "琼华", "琼英", "琼莹", "缉熙", "修能", "辰良", "昭质", "明修", "兰芷",
    "清圆", "幽意", "素月", "韶明", "清润", "幽芳", "清晓", "新霁", "凝碧",
    "鹤吟", "幽韵", "初蕊", "初晴", "疏星", "凌绝", "朝槿", "凝竹", "知新",
    "博文", "星汉", "清尘", "澄波", "清辉", "暗香", "清浅", "幽深", "初月",
    "凌波", "景明",
}

# 3 分：兜底。能用、不土，但平庸或偏景物；优选池（4 分以上）不够时才会出场，
# 抽样权重不加分，故始终排在 4/5 分之后。
OK = {
    "令闻", "佳辰", "兰润", "凝芳", "初阳", "初雪", "初霁", "初静", "华年",
    "南星", "南熏", "博衍", "回雪", "如圭", "如璧", "妍华", "宜夏", "岁华",
    "微薰", "心月", "新晴", "明霞", "映秋", "晓露", "晚晴", "晴远", "桂堂",
    "梅影", "檀心", "沅芷", "浅黛", "清时", "清景", "清标", "清遥", "清秋",
    "玉清", "琼枝", "琼树", "疏香", "知春", "竹青", "蕙风", "青柯", "香凝",
    "鸣佩", "修文",
}

# 人工逐条确认为 1 分的样例（不是全量——全量 568 个默认屏蔽，这里只留审查证据，
# 供「为什么这个不出」的追溯与回归用）。注意：本表与 OK 及以上不得重叠。
BAN_EXTRA = {
    "仁月", "月娟", "宛风", "意绪", "红蘸", "碧红", "红微", "紫艳", "书明",
    "明基", "玉明", "文骨", "信续", "长衍", "问孟", "米粟", "水溢", "义质",
    "信如", "厚薄", "立朝", "民恩", "游元", "殷芒", "来歌", "游歌", "允维",
    "显思", "祈黄", "仪成", "维天", "齐明", "宁耕", "保真", "修好", "中情",
    "高厉", "耀玉", "生水", "宜生", "宝兴", "文彩", "信成", "贤德", "淑真",
    "承恩", "承欢", "长乐", "长寻", "半羞", "微颦", "静珍", "容光", "兰沐",
    "凝情", "香平", "香闲", "香砌", "椒闲", "兰焰", "兰和", "兰思", "玉莺",
    "金镂", "金香", "金凤", "银涛", "翠娥", "翠眉", "轻翠", "簇翠", "金翠",
    "玉瓒", "黄流", "蒹葭", "澧兰", "窈窕", "伊人", "金锡", "繁祉", "景福",
    "蔼吉", "如磨", "文武", "仪成", "文宪", "甘雨", "流泉", "顺德",
    "淑君", "温恭", "河洲", "玉英", "芳泽", "芳华", "高厉", "文耀", "诚信",
    "凤翔", "石泉", "松柏", "秋菊", "木兰", "光明", "济天", "光昭", "贤明",
    "乐诚", "正兴", "礼乐", "仁义", "春翔", "山高", "海深", "饮泉", "芝草",
    "芝英", "桂兰", "日月", "金阶", "随风", "厚德", "明德", "中和", "敏慎",
    "博学", "笃志", "敦厚", "俊杰", "精微", "善忠", "善养", "山木", "霜露",
    "文德", "仁爱", "天高", "礼智", "泉达", "明著", "乔木", "幽谷",
    "绰裕", "知穆", "宗美", "悠远", "博厚", "高明", "善推", "君道", "仁政",
    "知学", "生知", "仁人", "仁亲", "问孟", "米粟", "水溢", "义质",
}


# 倒序单独定级：语料里的字对只有原句语序，引擎却会按音韵挑字序，所以倒序必须
# 另判一次。未在此表出现的倒序一律按屏蔽处理——「幽韵」可用不等于「韵幽」可用。
REV = {
    # 4 分
    "鸣鹤": 4, "扬清": 4, "清婉": 4, "松乔": 4, "修明": 4, "芷兰": 4,
    "蕊初": 4, "文博": 4,
    # 3 分（兜底）
    "嘉柔": 3, "影疏": 3, "远致": 3, "华琼": 3, "良辰": 3, "意幽": 3,
    "晓清": 3, "碧凝": 3, "晴初": 3, "星疏": 3, "尘清": 3, "波澄": 3,
    "深幽": 3, "明景": 3, "文修": 3, "润兰": 3, "芳凝": 3, "阳初": 3,
    "雪初": 3, "霁初": 3, "静初": 3, "华妍": 3, "夏宜": 3, "月心": 3,
    "秋映": 3, "黛浅": 3, "时清": 3, "景清": 3, "秋清": 3, "青竹": 3,
    "凝香": 3,
}


# 名字感补库（data/poetry/poetry_extra.json）新增字对的定级。
# 单独一表而不是并进 TOP/GOOD/OK：补库随时可能整份回退，删除本表即可复原，
# 不必在多处翻找哪几个字对是后加的。
EXTRA = {
    # 5 分
    "静好": 5, "舜华": 5, "扶苏": 5, "子衿": 5, "景行": 5, "思齐": 5,
    "望舒": 5, "宜修": 5, "杜若": 5, "若英": 5,
    # 4 分
    "柔荑": 4, "琼琚": 4, "子佩": 4, "思存": 4, "松茂": 4, "月恒": 4,
    "菁莪": 4, "未央": 4, "云汉": 4, "穆清": 4, "采芹": 4, "令德": 4,
    "灵均": 4, "芳菲": 4, "沐芳": 4, "素华": 4, "云衣": 4, "秉德": 4,
    "素荣": 4, "南枝": 4, "守拙": 4, "夕佳": 4,
    "东篱": 4, "出岫": 4, "舒啸": 4, "成绮": 4, "云起": 4, "钟秀": 4,
    "碧霄": 4,
    # 3 分（兜底）
    "琼瑶": 3, "霓裳": 3, "婉若": 3, "春松": 3, "澄静": 3, "潮生": 3,
    "海平": 3, "纤尘": 3, "暖树": 3, "新燕": 3, "潭清": 3,
}

# 补库字对的倒序（同 REV，未列出即屏蔽）
EXTRA_REV = {
    "存思": 3, "茂松": 3, "清穆": 3, "佳夕": 3, "修宜": 3,
}


def build_taste(out: Path) -> None:
    """产出 pair_taste.json：TOP→5、GOOD→4、OK→3，其余一律 1（默认屏蔽）。

    白名单是**唯一出口**：任何新增字对若未在此定级，都按 1 分处理（不出），
    以保证「语料扩充」不会把旧毛病带回来。漏定的代价是名字变少（可见、可测），
    而不是默默变土（不可见）——这是刻意选择的安全侧。
    """
    rows = flatten(load_pairs())
    words = sorted({w for w, _ in rows})
    scores: dict[str, int] = {}
    for w in words:
        if w in TOP:
            scores[w] = 5
        elif w in GOOD:
            scores[w] = 4
        elif w in OK:
            scores[w] = 3
        elif w in EXTRA:
            scores[w] = EXTRA[w]
        else:
            scores[w] = 1
    # 倒序：显式定级覆盖（可能与某个正序同名，冲突要报出来）
    for w, s in {**REV, **EXTRA_REV}.items():
        if w in scores and scores[w] != s:
            print(f"[taste] 警告：{w} 正序 {scores[w]} 分与倒序 {s} 分冲突，以倒序为准")
        scores[w] = s

    out.write_text(
        json.dumps(
            {"_meta": {"判据": "愿不愿意写在出生证明上",
                       "levels": "5=优先 4=可用 3=兜底 1=屏蔽",
                       "policy": "白名单外默认 1（屏蔽）；未定级的新字对不出"},
             "scores": scores},
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    dist = {s: sum(1 for v in scores.values() if v == s) for s in (5, 4, 3, 1)}
    print(f"[taste] {len(words)} 个字对 → {dist}")
    overlap = (TOP & GOOD) | (TOP & OK) | (GOOD & OK)
    if overlap:
        print(f"[taste] 警告：同一字对出现在多个档位 {sorted(overlap)}")
    contradict = BAN_EXTRA & (TOP | GOOD | OK)
    if contradict:
        print(f"[taste] 警告：既在屏蔽样例又在白名单 {sorted(contradict)}")
    stray = (TOP | GOOD | OK | set(EXTRA)) - set(words)
    if stray:
        print(f"[taste] 警告：定级了语料里不存在的字对 {sorted(stray)}")
    for s, names in ((5, TOP), (4, GOOD), (3, OK)):
        print(f"  {s} 分（{len(names)}）：", " ".join(sorted(names)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="分层抽样条数")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--build", action="store_true", help="按白名单+规则生成 pair_taste.json")
    ap.add_argument("--apply", default="", help="评分 JSON 路径（应用过滤）")
    ap.add_argument("--min-score", type=int, default=4, help="保留阈值，默认 4")
    args = ap.parse_args()

    if args.build:
        build_taste(PROJECT_ROOT / "data" / "poetry" / "pair_taste.json")
        return
    if args.apply:
        do_apply(Path(args.apply), args.min_score)
        return
    if args.sample:
        do_sample(args.sample, Path(args.out))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
