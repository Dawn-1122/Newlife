"""
v2 起名流程测试：来源推荐（寓意优先/命格优先）+ 黑名单分级

覆盖：
- 黑名单分级：情绪字拆出硬拦截、事件字仍硬拦、情绪字软门槛
- 来源推荐：命格优先排序、寓意优先忌神避让
- 来源选字：喜用神字排前
"""

import pytest

from app.services.naming_engine import NamingEngine
from app.core.constants import NEGATIVE_CHARS, EMOTIONAL_CHARS


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


# ── 黑名单分级（优先级3） ──

def test_emotional_chars_separated_from_negative():
    """情绪字已从硬拦截名单拆出，两集合无交集。"""
    assert not (NEGATIVE_CHARS & EMOTIONAL_CHARS)
    assert "悲" in EMOTIONAL_CHARS
    assert "恨" in EMOTIONAL_CHARS
    assert "匪" in NEGATIVE_CHARS
    assert "丧" in NEGATIVE_CHARS
    assert "死" in NEGATIVE_CHARS


def test_event_chars_still_blocked_in_pool(engine):
    """事件类字不进候选池。"""
    chars = engine._select_candidate_chars(
        ["火"], "male", 2, set(NEGATIVE_CHARS), None
    )
    charset = {c["char"] for c in chars}
    for bad in ["匪", "丧", "死", "病", "偷", "劫", "瘟", "疫"]:
        assert bad not in charset


def test_emotional_chars_enter_pool(engine):
    """情绪字进入候选池（不再硬拦截）。"""
    chars = engine._select_candidate_chars(
        ["火", "土", "木"], "male", 2, set(NEGATIVE_CHARS), None
    )
    charset = {c["char"] for c in chars}
    entered = [c for c in EMOTIONAL_CHARS if c in charset]
    assert entered, "情绪字应进入候选池"


def test_emotional_char_without_provenance_rejected(engine):
    """情绪字软门槛：无出处的情绪字名字不放行。"""
    chars_info = [engine.char_db.get_char("悲")]
    r = engine._evaluate_name("李", "悲", chars_info, None, None)
    assert r is None


# ── 来源推荐（寓意优先/命格优先） ──

def test_recommend_sources_bazi_first(engine):
    """命格优先：返回八字解释 + 来源按喜用神倾向排序。"""
    r = engine.recommend_sources(
        surname="李", gender="female",
        year=2020, month=5, day=20, mode="bazi_first", limit=10,
    )
    assert r["mode"] == "bazi_first"
    assert r["bazi_explanation"] is not None
    assert "xi_wuxing" in r["bazi_explanation"]
    assert "suggestion" in r["bazi_explanation"]
    assert r["sources"]
    assert r["sources"][0]["bazi_flag"] == "xiyong"


def test_recommend_sources_meaning_first(engine):
    """寓意优先：命中寓意的来源排前，忌神倾向标记 ji。"""
    r = engine.recommend_sources(
        surname="李", gender="female",
        year=2020, month=5, day=20, mode="meaning_first",
        meanings=["gentle"], limit=10,
    )
    assert r["mode"] == "meaning_first"
    assert r["sources"]
    assert any("寓意" in s["match_reason"] for s in r["sources"])


def test_recommend_sources_has_wuxing_tendency(engine):
    """每个来源都带五行倾向字段。"""
    r = engine.recommend_sources(
        surname="李", gender="female", year=2020, month=5, day=20, limit=5,
    )
    for s in r["sources"]:
        assert "wuxing_tendency" in s
        assert "wuxing_dist" in s


# ── 来源选字 ──

def test_source_chars_xiyong_first(engine):
    """来源选字：喜用神字排在忌神字之前。"""
    r = engine.recommend_sources(
        surname="李", gender="female",
        year=2020, month=5, day=20, mode="bazi_first", limit=3,
    )
    ids = [s["id"] for s in r["sources"]]
    rc = engine.source_chars(
        surname="李", gender="female", year=2020, month=5, day=20,
        source_ids=ids, limit_per_source=8,
    )
    assert rc["sources"]
    for src in rc["sources"]:
        flags = [c["bazi_flag"] for c in src["chars"]]
        if "xiyong" in flags and "ji" in flags:
            assert flags.index("xiyong") < flags.index("ji")


# ── 姓氏谐音嵌诗 + 谐音借力（优先级4/5） ──

def test_surname_homophone_boost(engine):
    """优先级4：姓谐音 + 名 = 褒义词。"""
    hit, phrase = engine.surname_fit.surname_homophone_boost("吴", "与伦")
    assert hit and phrase == "无与伦比"
    hit2, phrase2 = engine.surname_fit.surname_homophone_boost("韩", "秋")
    assert hit2 and phrase2 == "寒秋"
    hit3, _ = engine.surname_fit.surname_homophone_boost("张", "伟强")
    assert not hit3


def test_name_phrase_boost(engine):
    """优先级5：名字本身是经典好词/典故。"""
    hit, _ = engine.surname_fit.name_phrase_boost("晨曦")
    assert hit
    hit2, _ = engine.surname_fit.name_phrase_boost("芷兰")
    assert not hit2


def test_s1_homophone_boost_score(engine):
    """谐音成词在 S1 维度体现为加分（8分）。"""
    assert engine.yunwei._s1_phrase_score("吴", "与伦", [{"char": c} for c in "与伦"], None) == 8
    assert engine.yunwei._s1_phrase_score("韩", "秋", [{"char": "秋"}], None) == 8


# ── 出处稀缺度（优先级1） ──

def test_provenance_famous_penalty(engine):
    """名句直取降档，冷门句满分（避烂大街）。

    注意：出处分现在按「组合成立度」分档，故对比必须在**同等成立度**下进行——
    用合成条目固定两字相邻，只让「是否名句」这一个变量变化。
    """
    from app.core.constants import FAMOUS_PHRASES
    y = engine.yunwei
    phrase = FAMOUS_PHRASES[0]

    base = {
        "id": "synthetic",
        "recommend_chars": ["清", "风"],
        "text": "清风入我怀",
        "imagery": [],
        "scene": "",
    }
    famous = dict(base, citation=f"《{phrase}》", title="")
    cold = dict(base, citation="《冷门篇》", title="")

    chars_info = [engine.char_db.get_char(c) for c in ("清", "风")]
    famous_score, _, famous_kind = y._provenance_score(chars_info, famous)
    cold_score, _, cold_kind = y._provenance_score(chars_info, cold)

    # 前置条件：两边的「组合成立度」必须相同，否则测的不是稀缺度
    assert famous_kind == cold_kind == "adjacent"
    assert famous_score < cold_score


def test_provenance_cohesion_tiers(engine):
    """同源分按组合成立度分档：原文成词 > 同句 > 跨句拼接。"""
    y = engine.yunwei
    db = engine.char_db

    def p(text):
        entry = {"id": "t", "recommend_chars": ["婵", "娟", "橘"], "text": text}
        chars = [db.get_char("婵"), db.get_char("娟")]
        return y._provenance_score(chars, entry)

    adjacent_score, same_source, kind = p("玉人千里共婵娟")
    assert same_source is True and kind == "adjacent"

    cross_entry = {"id": "t", "recommend_chars": ["婵", "橘"], "text": "婵娟千里，橘柚飘香"}
    cross_score, _, cross_kind = y._provenance_score(
        [db.get_char("婵"), db.get_char("橘")], cross_entry
    )
    assert cross_kind == "cross_clause"
    assert adjacent_score > cross_score, "原文成词必须高于跨句拼接"


def test_pair_cohesion_kinds():
    """成立度不分词函数：相邻/同句/跨句/字不在原文。"""
    from app.services.yunwei_scorer import pair_cohesion

    assert pair_cohesion("婵", "娟", "共婵娟") == "adjacent"
    assert pair_cohesion("灼", "华", "桃之夭夭，灼灼其华") == "same_clause"
    assert pair_cohesion("红", "黄", "白酒红萸，黄花绿橘") == "cross_clause"
    assert pair_cohesion("清", "风", "山高水长") == "char_absent"
    assert pair_cohesion("清", "风", "") == "cross_clause"


# ── 词性标注 + 动名组合（优先级2） ──

def test_verb_noun_coherence(engine):
    """动名结构（风眠/凝香）在 C 维度加分。"""
    db = engine.char_db
    y = engine.yunwei

    def c_score(given):
        chars_info = [db.get_char(c) for c in given if db.get_char(c)]
        return y._coherence_score(chars_info)

    assert c_score("风眠") == 5
    assert c_score("凝香") == 5
