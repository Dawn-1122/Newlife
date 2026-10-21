"""
偏好体系测试：寓意/风格扩充 + 意象词族 + 偏好硬分流

覆盖：
- 寓意扩到 12、风格扩到 8
- 每个寓意的意象词族能命中出处数据（偏好真正连通数据）
- 偏好生效：不同寓意 → 来源推荐、名字生成结果显著不同
"""

import pytest

from app.services.naming_engine import NamingEngine
from app.core.naming_options import MEANING_OPTIONS, STYLE_OPTIONS


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


# ── 枚举扩充 ──

def test_meaning_options_expanded():
    """寓意扩到 14 个，新增乐观豁达/坚韧不拔，且全部带分组。"""
    assert len(MEANING_OPTIONS) == 14
    for code in ["beauty", "loyal", "patriotic", "tranquil", "resilient", "optimistic"]:
        assert code in MEANING_OPTIONS
    # 每个寓意都有意象词族（治本关键）+ 分组（前端按方向分块渲染）
    for code, opt in MEANING_OPTIONS.items():
        assert opt.get("imagery_words"), f"{code} 缺少 imagery_words"
        assert opt.get("group"), f"{code} 缺少 group"


def test_style_options_expanded():
    """风格扩到 8 个，新增温润内敛/清朗俊逸/质朴厚重/空灵禅意。"""
    assert len(STYLE_OPTIONS) == 8
    for code in ["warm", "elegant", "plain", "zen"]:
        assert code in STYLE_OPTIONS


# ── 意象词族连通数据 ──

def test_meaning_imagery_words_hit_data(engine):
    """每个寓意的意象词族都能命中出处数据（不再是两套词汇对不上）。"""
    entries = engine._available_source_entries("male", set())
    blobs = [
        " ".join(e.get("imagery", []) or []) + " "
        + (e.get("scene", "") or "") + " "
        + (e.get("text", "") or "")
        for e in entries
    ]
    for code, opt in MEANING_OPTIONS.items():
        words = opt["keywords"] + opt.get("imagery_words", [])
        hits = sum(1 for b in blobs if any(kw in b for kw in words))
        assert hits > 0, f"寓意 {code}({opt['name']}) 词族在数据中零命中"


# ── 偏好硬分流 ──

def test_preference_changes_source_recommendation(engine):
    """选「勇敢」vs「美丽」→ 来源推荐 top 应显著不同。"""
    a = engine.recommend_sources(
        "李", "male", 2018, 5, 10, 12, 0,
        mode="meaning_first", meanings=["bravery"], limit=30,
    )
    b = engine.recommend_sources(
        "李", "male", 2018, 5, 10, 12, 0,
        mode="meaning_first", meanings=["beauty"], limit=30,
    )
    ta = [s["title"] for s in a["sources"]]
    tb = [s["title"] for s in b["sources"]]
    overlap = len(set(ta) & set(tb))
    assert overlap < len(ta) * 0.6, f"偏好未生效：来源重叠 {overlap}/{len(ta)}"


def test_preference_changes_generated_names(engine):
    """选「勇敢」vs「美丽」→ **展示出来的**那一批名字应显著不同。

    按展示口径（一次 6 个）断言，而不是按 max_results=30：引擎会把全部候选都返回，
    而某个姓氏在名字感闸门后可用的名字可能只有二三十个——此时两次调用返回的是
    同一批名字，只是排序不同，集合重合度天然接近 100%。界面一次只给 6 个，
    「偏好有没有用」取决于这 6 个换不换，故以此为准。
    """
    a = engine.generate_names(
        "李", "male", 2018, 5, 10, 12, 0,
        name_length=2, max_results=6, meanings=["bravery"],
    )
    b = engine.generate_names(
        "李", "male", 2018, 5, 10, 12, 0,
        name_length=2, max_results=6, meanings=["beauty"],
    )
    na = [n["full_name"] for n in a["names"]]
    nb = [n["full_name"] for n in b["names"]]
    assert na and nb, "两种偏好都应有结果"
    overlap = len(set(na) & set(nb))
    assert overlap < len(na) * 0.6, f"偏好未生效：名字重叠 {overlap}/{len(na)}"
    assert set(na[:3]) - set(nb[:3]), "前三名完全一致 —— 偏好没有影响排序"


def test_new_meaning_works(engine):
    """新增寓意（家国）能正常推荐来源，且返回来源契合家国意象。"""
    r = engine.recommend_sources(
        "李", "male", 2018, 5, 10, 12, 0,
        mode="meaning_first", meanings=["patriotic"], limit=20,
    )
    assert r["total"] > 0
    # 前若干来源应含「契合寓意」标记（命中偏好）
    hit = sum(1 for s in r["sources"] if "契合寓意" in (s.get("match_reason") or ""))
    assert hit > 0, "家国寓意应命中若干来源"
