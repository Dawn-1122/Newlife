"""释名收束语（页面上叫「整体印象」）。

为什么需要：释名页此前是「用字解析 / 音律分析 / 五格数理 / 八字匹配 / 诗词出处」
五块依据的堆叠。每一块都算得对，读完却不知道该记住什么 —— 用户拿着一屏数据，
没有得到一句话告诉他「这个名字读起来是什么感觉」。

边界（与全产品一致，写在这里是要挡住后来的改动）：
1. 只描述**已经算出来的事实**（用字五行、声调搭配、笔画数理、喜用呼应）。
2. 不判吉凶、不预测、不出现「必定」「将来」「一生」这类定论话术。
   五格一项只说结构，口径与 `WugeScorer._describe` 一致。
3. 句子随数据变化，不是一段固定文案 —— 固定文案在第三次释名时就露馅了。
4. 收尾一句固定基调（下面 `CODAS`），按姓名稳定取一条：
   同一个名字每次得到的收束语完全一致，不会「刷新一次换一种说法」。
"""

from __future__ import annotations

from app.services.phonetics import PhoneticsScorer

WUXING_ORDER = ("金", "木", "水", "火", "土")

# 收束句：都是「名字到此为止」的意思，不承诺任何结果。
# 三条轮换是为了避免连续释名时反复读到同一句，又保证同名的结果恒定。
CODAS = (
    "名字是起手的一笔，后面的笔画由人来写。",
    "这些只是名字本身的分寸，往后的路不在这里定。",
    "名字能定的只到这里，剩下的交给日子。",
)


def _quote(chars: list[str]) -> str:
    # 中文里并列引号不加顿号：「清」「野」二字
    return "".join("「%s」" % c for c in chars)


def _subject(chars: list[str]) -> str:
    """用字主语：单字名不说「二字」。"""
    if not chars:
        return "这个名字"
    if len(chars) == 1:
        return "名中「%s」一字" % chars[0]
    return _quote(chars) + "二字"


def _pick(seq, key: str):
    """按字符串稳定取一项（不依赖 hash 随机化，跨进程一致）。"""
    if not seq:
        return None
    total = 0
    for ch in key:
        total += ord(ch)
    return seq[total % len(seq)]


# --------------------------------------------------------------------------- #
# 分句
# --------------------------------------------------------------------------- #

def _sentence_chars(chars: list[str], chars_info: list[dict]) -> str:
    """用字与五行：只描述分布，不讲相生相克（那是判吉凶的入口）。"""
    if not chars:
        return ""
    wuxings = [(ci.get("wuxing") or "") for ci in chars_info]
    known = [w for w in wuxings if w in WUXING_ORDER]

    if not known:
        return "%s，字库中暂无五行归属，用字本身仍按音与义看。" % _subject(chars)

    if len(chars) == 1:
        return "名中「%s」一字，属%s。" % (chars[0], known[0])

    if len(set(known)) == 1:
        return "%s同属%s，用字落在同一行。" % (_subject(chars), known[0])

    if len(known) == 1:
        # 两字里只有一个查到五行：另一字是生僻字或字库未收，如实说明
        owner = ("", "")
        for c, w in zip(chars, wuxings):
            if w in WUXING_ORDER:
                owner = (c, w)
                break
        return "%s，其中「%s」属%s，另一字字库暂无归属。" % (
            _subject(chars), owner[0], owner[1]
        )

    distinct = list(dict.fromkeys(known))
    if len(distinct) == 2 and len(chars) == 2:
        return "%s，一属%s、一属%s，用字不拘一行。" % (
            _subject(chars), distinct[0], distinct[1]
        )

    pairs = "、".join(
        "「%s」属%s" % (c, w) for c, w in zip(chars, wuxings) if w in WUXING_ORDER
    )
    return "%s，%s，用字不拘一行。" % (_subject(chars), pairs)


def _sentence_phonetics(phonetics: dict) -> str:
    """音律：先看声调形态（全平/全仄/相间），再按评分决定语气。

    早期只按分数分档，结果「仄仄仄」拿到 57 分也被写成「略平」——
    说的是平地，实际全是仄声，读过音律卡的人当场就能发现对不上。
    """
    rhythm = (phonetics or {}).get("rhythm") or ""
    score = (phonetics or {}).get("score") or 0
    tone_types = (phonetics or {}).get("tone_types") or []
    if not rhythm:
        return ""

    kinds = {t for t in tone_types if t in ("平", "仄")}
    if len(tone_types) >= 2 and len(kinds) == 1:
        # 全平或全仄：只陈述形态与听感，不说好坏（改名与否不由这里决定）。
        # 拗口门槛直接取评分器的常量，免得两处各定一套标准。
        which = next(iter(kinds))
        flat = score < PhoneticsScorer.CACOPHONOUS_MIN_SCORE
        if which == "平":
            tail = "但起伏太少，几字连读容易糊在一起" if flat else "起伏少一些"
            return "声调全落在平声，念着舒展，%s。" % tail
        tail = "几字连读会有点顶" if flat else "起伏少一些"
        return "声调全落在仄声，念着短促，%s。" % tail

    if score >= 85:
        return "声调走%s，平仄相间，有起伏而不拗口。" % rhythm
    if score >= 70:
        return "声调走%s，平仄相间，念起来不费劲。" % rhythm
    return "声调走%s，有起伏，个别字连读略拗，放慢些就顺了。" % rhythm


def _sentence_wuge(wuge: dict) -> str:
    """五格：只说笔画结构，绝不出现吉/凶（口径同 WugeScorer._describe）。"""
    score = (wuge or {}).get("total_score") or 0
    if not score:
        return ""
    if score >= 85:
        return "笔画数理分布均衡。"
    if score >= 70:
        return "笔画数理平稳，没有明显的陡起陡落。"
    if score >= 55:
        return "笔画数理有起伏，属常见范围。"
    return "笔画数理起伏较大，只影响这一项，音与义不受牵连。"


def _sentence_bazi(bazi_match: dict | None) -> str:
    """八字：只说「对得上 / 没补上」，且明确「不构成减分」。"""
    if not bazi_match:
        return ""
    xiyong = (((bazi_match.get("bazi") or {}).get("xiyong") or {}).get("xi_wuxing")) or []
    matched = bazi_match.get("matched_wuxing") or []
    if not xiyong:
        return ""

    if matched:
        return "用字里有属%s的字，与喜用%s对得上。" % (
            "、".join(dict.fromkeys(matched)),
            "、".join(xiyong),
        )
    return "喜用%s，用字五行不在其中，这一项没有补益，名字本身不受影响。" % "、".join(xiyong)


# --------------------------------------------------------------------------- #
# 对外
# --------------------------------------------------------------------------- #

def build_verdict(analysis: dict) -> str:
    """把一次释名结果收成一段话。

    :param analysis: 与 `/analyze` 返回结构相同的 dict
        （需含 chars_info / phonetics / wuge，bazi_match 可选）
    """
    analysis = analysis or {}
    chars_info = analysis.get("chars_info") or []
    chars = [ci.get("char") or "" for ci in chars_info]
    chars = [c for c in chars if c]

    sentences = [
        _sentence_chars(chars, chars_info),
        _sentence_phonetics(analysis.get("phonetics") or {}),
        _sentence_wuge(analysis.get("wuge") or {}),
        _sentence_bazi(analysis.get("bazi_match")),
    ]
    text = "".join(s for s in sentences if s)

    full_name = analysis.get("full_name") or "".join(
        ([analysis.get("surname") or ""] + chars)
    )
    coda = _pick(CODAS, full_name)
    return text + coda
