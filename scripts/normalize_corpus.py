"""
T1 · 语料规范化：把 chinese-poetry 原始语料清洗成统一中间格式 raw_corpus.jsonl

覆盖 6 大类：诗经 / 楚辞 / 唐诗 / 宋词 / 汉魏古诗 / 经史子集。
- 繁体转简体（opencc t2s）
- 摘句（切句后取 4~24 字、含字库吉字、无负面字黑名单的片段）
- 统一字段：{id, source, title, author, dynasty, text, original_text, citation, provenance}
- 预筛 500~800 条候选（冗余，供后续精选 400~500）

用法：
    venv/bin/python scripts/normalize_corpus.py
    venv/bin/python scripts/normalize_corpus.py --corpus .corpus --out data/poetry/raw_corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from poetry_utils import PROJECT_ROOT, load_lucky_chars, load_blacklist

try:
    from opencc import OpenCC
    _CC = OpenCC("t2s")
    def to_simplified(text: str) -> str:
        return _CC.convert(text)
except ImportError:  # 未安装 opencc 时原样返回（会保留繁体，需人工注意）
    def to_simplified(text: str) -> str:
        return text


CORPUS_DIR = PROJECT_ROOT / ".corpus"
DEFAULT_OUT = PROJECT_ROOT / "data" / "poetry" / "raw_corpus.jsonl"

# 每类候选条数配额（合计约 700）
QUOTA = {
    "诗经": 120,
    "楚辞": 55,
    "唐诗": 150,
    "宋词": 120,
    "汉魏古诗": 40,
    "经史子集": 200,
}

# 正面意象关键词（命中加分，帮助优先摘取适合起名的句子）
POSITIVE_KEYWORDS = (
    "美", "华", "芳", "玉", "明", "清", "德", "嘉", "兰", "竹",
    "风", "云", "山", "水", "光", "辉", "昭", "景", "春", "秋",
    "月", "星", "雪", "梅", "菊", "松", "柏", "谦", "诚", "信",
    "善", "仁", "义", "礼", "智", "宁", "安", "泰", "和", "瑞",
    "祥", "雅", "淑", "静", "婉", "慧", "敏", "杰", "俊", "贤",
    "君", "泽", "润", "涵", "怡", "乐", "康", "健", "承", "弘",
    "志", "远", "新", "维", "博", "文", "修", "正", "中", "平",
)

# 名篇名句核心短语（命中即大幅加分，确保预筛出的候选偏向「适合起名的名句」）
FAMOUS_CORES = (
    # 诗经
    "桃之夭夭", "灼灼其华", "关关雎鸠", "窈窕淑女", "君子好逑",
    "蒹葭苍苍", "在水一方", "呦呦鹿鸣", "鹤鸣九皋", "声闻于天",
    "有匪君子", "如切如磋", "如琢如磨", "周虽旧邦", "其命维新",
    "静女其姝", "野有蔓草", "清扬婉兮", "笾豆静嘉", "瞻彼淇奥",
    "绿竹猗猗", "瑟彼玉瓒", "既醉以酒",
    # 楚辞
    "路漫漫其修远", "上下而求索", "纷吾既有此内美", "重之以修能",
    "吉日兮辰良", "浴兰汤兮沐芳", "华采衣兮若英", "沅有芷兮澧有兰",
    "芳与泽其杂糅", "唯昭质其犹未亏", "光风转蕙", "与天地兮同寿",
    "与日月兮同光", "登昆仑兮食玉英", "怀兰英兮把琼若",
    # 唐诗
    "会当凌绝顶", "一览众山小", "天生我材必有用", "千金散尽还复来",
    "明月松间照", "清泉石上流", "春风得意马蹄疾", "一日看尽长安花",
    "海内存知己", "天涯若比邻", "长风破浪会有时", "直挂云帆济沧海",
    "欲穷千里目", "更上一层楼", "大鹏一日同风起", "扶摇直上九万里",
    "海上生明月", "天涯共此时", "会须一饮三百杯", "山光悦鸟性",
    "潭影空人心", "曲径通幽处", "禅房花木深",
    # 宋词
    "但愿人长久", "千里共婵娟", "大江东去", "千古风流人物",
    "众里寻他千百度", "灯火阑珊", "莫等闲", "白了少年头",
    "三十功名尘与土", "八千里路云和月", "明月几时有", "把酒问青天",
    "零落成泥碾作尘", "只有香如故", "衣带渐宽终不悔", "山重水复疑无路",
    # 汉魏古诗（曹操）
    "山不厌高", "海不厌深", "周公吐哺", "天下归心", "老骥伏枥",
    "志在千里", "烈士暮年", "壮心不已", "日月之行", "若出其中",
    "星汉灿烂", "若出其里", "对酒当歌",
    # 经史子集
    "天行健", "君子以自强不息", "地势坤", "君子以厚德载物",
    "大学之道", "在明明德", "致中和", "天地位焉", "学而时习之",
    "温故而知新", "敏于事而慎于言", "见贤思齐", "博学而笃志",
    "切问而近思", "老吾老以及人之老", "富贵不能淫", "贫贱不能移",
    "威武不能屈", "穷则独善其身", "达则兼济天下", "知者不惑",
    "仁者不忧", "勇者不惧", "修身齐家治国平天下",
)

# 摘句时剥离的前缀（子曰/孟子曰等）
SPEAKER_PREFIX = re.compile(
    r"^(?:子曰|曾子曰|有子曰|子夏曰|子贡曰|子游曰|子张曰|孟子曰|"
    r"孔子曰|仲尼曰|颜渊曰|子路曰|冉有曰|君子曰|太史公曰|曰)[:：]?"
)
# 摘句时剥离的引号/书名号
STRIP_CHARS = "「」『』“”\"'《》（）()·．—… "


def is_cjk(ch: str) -> bool:
    """判断是否为汉字（CJK 统一表意文字）。"""
    return "\u4e00" <= ch <= "\u9fff"


def clean_excerpt(raw: str) -> str:
    """清洗摘句：去前缀、去引号、去空白。"""
    text = raw.strip()
    text = SPEAKER_PREFIX.sub("", text)
    text = text.strip(STRIP_CHARS)
    text = re.sub(r"\s+", "", text)
    return text


def char_len(text: str) -> int:
    return sum(1 for ch in text if is_cjk(ch))


def split_excerpts(paragraphs: list[str]) -> list[str]:
    """把段落切分成候选摘句（按句读切，过滤空段）。"""
    joined = "\n".join(paragraphs)
    parts = re.split(r"[。！？；\n]", joined)
    excerpts: list[str] = []
    for part in parts:
        clean = clean_excerpt(part)
        if not clean:
            continue
        excerpts.append(clean)
    return excerpts


def score_excerpt(text: str, lucky: set[str], blacklist: set[str]) -> int:
    """给摘句打「适合起名」分（越高越好）。"""
    chars = [c for c in text if is_cjk(c)]
    if not (4 <= len(chars) <= 24):
        return -1
    if any(c in blacklist for c in chars):
        return -1
    lucky_count = sum(1 for c in chars if c in lucky)
    if lucky_count < 1:
        return -1
    pos_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    score = lucky_count * 3 + pos_hits * 2 + (1 if len(chars) <= 12 else 0)
    # 名篇名句大幅加分
    if any(core in text for core in FAMOUS_CORES):
        score += 100
    # 惩罚过长摘句（名句通常短小精炼）
    if len(chars) > 16:
        score -= (len(chars) - 16)
    return score


def read_json_list(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "paragraphs" in data:
        return [data]
    return []


def iter_poems(source: str, corpus_dir: Path) -> list[dict]:
    """按来源读取原始 poem，产出 [{title, author, dynasty, paragraphs, citation_prefix, provenance}]。"""
    poems: list[dict] = []

    def add(title, author, dynasty, paragraphs, provenance):
        poems.append({
            "title": to_simplified(title),
            "author": to_simplified(author),
            "dynasty": dynasty,
            "paragraphs": [to_simplified(p) for p in paragraphs],
            "provenance": provenance,
        })

    if source == "诗经":
        for item in read_json_list(corpus_dir / "诗经" / "shijing.json"):
            chapter = item.get("chapter", "")
            section = item.get("section", "")
            base = item.get("title", "")
            # 国风用「风名·篇名」（周南·关雎），雅/颂用「小雅/大雅/周颂·篇名」
            if chapter == "国风":
                title = f"{section}·{base}" if section else base
            else:
                title = f"{chapter}·{base}"
            add(title, "佚名", "周", item.get("content", []),
                "chinese-poetry/诗经/shijing.json")
    elif source == "楚辞":
        for item in read_json_list(corpus_dir / "楚辞" / "chuci.json"):
            add(item.get("title", ""), item.get("author", "屈原"), "战国",
                item.get("content", []), "chinese-poetry/楚辞/chuci.json")
    elif source == "唐诗":
        for item in read_json_list(corpus_dir / "全唐诗" / "唐诗三百首.json"):
            title = clean_tang_title(item.get("title", ""))
            add(title, item.get("author", "佚名"), "唐",
                item.get("paragraphs", []), "chinese-poetry/全唐诗/唐诗三百首.json")
    elif source == "宋词":
        for item in read_json_list(corpus_dir / "宋词" / "宋词三百首.json"):
            add(item.get("rhythmic", ""), item.get("author", "佚名"), "宋",
                item.get("paragraphs", []), "chinese-poetry/宋词/宋词三百首.json")
    elif source == "汉魏古诗":
        for item in read_json_list(corpus_dir / "曹操诗集" / "caocao.json"):
            add(item.get("title", ""), "曹操", "汉末",
                item.get("paragraphs", []), "chinese-poetry/曹操诗集/caocao.json")
    elif source == "经史子集":
        for item in read_json_list(corpus_dir / "论语" / "lunyu.json"):
            chapter = item.get("chapter", "").rstrip("篇")
            add(f"论语·{chapter}", "孔子", "春秋", item.get("paragraphs", []),
                "chinese-poetry/论语/lunyu.json")
        for name, author in [("大学", "曾子"), ("中庸", "子思")]:
            path = corpus_dir / "四书五经" / ({"大学": "daxue.json", "中庸": "zhongyong.json"}[name])
            for item in read_json_list(path):
                add(name, author, "春秋", item.get("paragraphs", []),
                    f"chinese-poetry/四书五经/{path.name}")
        for item in read_json_list(corpus_dir / "四书五经" / "mengzi.json"):
            chapter = item.get("chapter", "")
            add(f"孟子·{chapter}", "孟子", "战国", item.get("paragraphs", []),
                "chinese-poetry/四书五经/mengzi.json")
    return poems


def build_citation(source: str, title: str) -> str:
    """拼接出处标注。"""
    if source in ("诗经", "楚辞"):
        return f"《{source}·{title}》"
    return f"《{title}》"


def clean_tang_title(title: str) -> str:
    """清洗唐诗标题：去乐府分类前缀、去尾部序号。"""
    title = to_simplified(title)
    title = re.sub(
        r"^(鼓吹曲辞|横吹曲辞|杂曲歌辞|相和歌辞|清商曲辞|杂歌谣辞|新乐府辞|舞曲歌辞|琴曲歌辞)\s*",
        "", title,
    )
    title = re.sub(r"\s*[一二三四五六七八九十]+\s*$", "", title)
    title = re.sub(r"\s*三首\s*[一二三四五]\s*$", "", title)
    return title.strip()


def normalize(corpus_dir: Path) -> list[dict]:
    """规范化主流程：读语料 → 摘句 → 打分 → 预筛候选。"""
    lucky = load_lucky_chars()
    blacklist = load_blacklist()

    candidates: list[dict] = []
    seen_text: set[str] = set()

    for source in ("诗经", "楚辞", "唐诗", "宋词", "汉魏古诗", "经史子集"):
        poems = iter_poems(source, corpus_dir)
        source_candidates: list[tuple[int, dict]] = []
        for poem in poems:
            original_text = "".join(poem["paragraphs"])
            for excerpt in split_excerpts(poem["paragraphs"]):
                score = score_excerpt(excerpt, lucky, blacklist)
                if score < 0:
                    continue
                text_key = f"{source}|{poem['title']}|{excerpt}"
                if text_key in seen_text:
                    continue
                seen_text.add(text_key)
                entry = {
                    "source": source,
                    "title": poem["title"],
                    "author": poem["author"],
                    "dynasty": poem["dynasty"],
                    "text": excerpt,
                    "original_text": original_text if len(original_text) <= 200 else original_text[:200],
                    "citation": build_citation(source, poem["title"]),
                    "provenance": poem["provenance"],
                }
                source_candidates.append((score, entry))

        # 每个来源取评分最高的前 quota 条
        source_candidates.sort(key=lambda x: (-x[0], x[1]["text"]))
        quota = QUOTA.get(source, 100)
        picked = [e for _, e in source_candidates[:quota]]
        candidates.extend(picked)
        print(f"[normalize] {source}: 原始 {len(poems)} 篇 → 候选摘句 {len(source_candidates)} → 预筛 {len(picked)} 条")

    # 分配稳定 id
    for i, entry in enumerate(candidates):
        entry["id"] = f"raw_{i + 1:04d}"

    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="规范化诗词语料")
    parser.add_argument("--corpus", default=str(CORPUS_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    corpus_dir = Path(args.corpus)
    candidates = normalize(corpus_dir)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in candidates:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[normalize] 完成，共预筛 {len(candidates)} 条 → {out_path}")


if __name__ == "__main__":
    main()
