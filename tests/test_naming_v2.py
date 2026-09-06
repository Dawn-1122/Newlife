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
    """名句直取降档，冷门句满分（避烂大街）。"""
    from app.core.constants import FAMOUS_PHRASES
    y = engine.yunwei
    famous_poem = None
    cold_poem = None
    for p in engine.poetry_db.get_all():
        text = " ".join([p.get("text", "") or "", p.get("citation", "") or "",
                         p.get("title", "") or ""])
        is_fam = any(ph in text for ph in FAMOUS_PHRASES)
        if is_fam and not famous_poem:
            famous_poem = p
        if not is_fam and not cold_poem:
            cold_poem = p
        if famous_poem and cold_poem:
            break

    def p_score(poem):
        rc = [c for c in poem["recommend_chars"] if engine.char_db.get_char(c)][:2]
        chars_info = [engine.char_db.get_char(c) for c in rc]
        return y._provenance_score(chars_info, poem)

    assert p_score(famous_poem) < p_score(cold_poem)


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
