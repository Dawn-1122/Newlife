"""
可选字表（/pickable-chars）契约测试。

这个接口是「先字后出处」路径的**前置质量闸门**：前端字表按它铺格子。
一旦字表与真实产能脱节，用户点到表里的字却拿到空结果，就会得出
「系统坏了」的结论——而这类偏差肉眼不可见（字表本身看起来完全正常），
所以必须用测试钉住。

两条核心契约：
1. **表内每个字都真的出得来名字**（无假阳性）；
2. **表外的字一个都出不来**（无假阴性）。

配套人工诊断：scripts/diag_selected_chars.py（--feasible 委托同一实现）。
"""

import pytest

from app.core.constants import (
    FILTERABLE_IMAGERY_FAMILIES,
    IMAGERY_FAMILY_PRIORITY,
    build_radical_family_map,
)
from app.services.naming_engine import NamingEngine


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


@pytest.fixture(scope="module")
def table_female(engine):
    """林/female 的可选字表（与姓氏强相关：林为阳平，三连同调会整类灭字）。"""
    return engine.pickable_chars(surname="林", gender="female")


def _produces(engine, surname, gender, char):
    r = engine.generate_names(
        surname=surname, gender=gender, name_length=2,
        max_results=30, use_bazi=False, selected_chars=[char],
    )
    return r["total"]


# ── 行为契约（与 live 对拍） ──

def test_table_chars_really_produce_names(engine, table_female):
    """表内抽 12 字：每个都必须真的出得来名字（无假阳性）。

    回归背景：初版入选条件写成「有搭档字或出得来名字」，把「有搭档但本姓氏
    下门槛全灭」的字也放进表里——姓林时「情」有 4 个已批准搭档（中/凝/兰/深），
    但 8 种字序全部三连同调，用户点到就是空表。
    """
    sample = [c["char"] for c in table_female["chars"]][:12]
    empty = [ch for ch in sample if _produces(engine, "林", "female", ch) == 0]
    assert not empty, f"可选字表里这些字实际产出为空：{empty}"


def test_bazi_mode_contract(engine):
    """开八字时的契约同样成立（这是资料页的默认状态，不能只测无八字口径）。

    八字会把候选池收窄到喜用神五行（林/female 553 → 331），
    门槛层还会排除「名字全忌神」的组合，两条变化都可能让字表与真实产出脱节。
    """
    bazi = dict(use_bazi=True, year=1994, month=5, day=20, hour=11, minute=0)
    table = engine.pickable_chars(surname="林", gender="female", **bazi)
    assert table["total"] < 553, "按喜用神筛过的池子应当更小"
    inside = [c["char"] for c in table["chars"]][:10]
    empty = [
        ch for ch in inside
        if engine.generate_names(
            surname="林", gender="female", name_length=2, max_results=30,
            selected_chars=[ch], **bazi,
        )["total"] == 0
    ]
    assert not empty, f"八字模式下这些表内字实际产出为空：{empty}"


def test_chars_outside_table_produce_nothing(engine, table_female):
    """表外抽 12 字：一个都不许出结果（无假阴性）。"""
    in_table = {c["char"] for c in table_female["chars"]}
    pool = [
        c["char"] for c in engine._select_candidate_chars(
            None, "female", 2, set(), None
        )
    ]
    outside = [ch for ch in pool if ch not in in_table][:12]
    assert outside, "池内字不该全部进表"
    leaked = [ch for ch in outside if _produces(engine, "林", "female", ch) > 0]
    assert not leaked, f"表外的字竟然出得来名字：{leaked}"


def test_every_row_has_name_hits(table_female):
    """行内一致性：name_hits > 0（入选依据）且 sample 非空。"""
    for row in table_female["chars"]:
        assert row["name_hits"] > 0, f"{row['char']} 入选但 name_hits=0"
        assert row["sample"], f"{row['char']} 没有示例名"


def test_counts_are_consistent(table_female):
    """计数自洽：feasible == 返回行数（未截断时），total >= feasible。"""
    assert table_female["total"] >= table_female["feasible"]
    if not table_female["truncated"]:
        assert table_female["feasible"] == len(table_female["chars"])
    assert table_female["returned"] == len(table_female["chars"])


# ── 意象族分组与排序 ──

def test_family_map_resolves_radical_overlap():
    """部首重叠必须按优先级定序：「日」同属火与日月星辰 → 归日月星辰。"""
    fam = build_radical_family_map()
    assert fam["日"] == "日月星辰"
    assert fam["禾"] == "草木" and fam["木"] == "草木"
    # 刀/刂 只用于名内呼应，不给用户当「金石意象」筛
    assert "刀" not in FILTERABLE_IMAGERY_FAMILIES["金"]
    assert "刂" not in FILTERABLE_IMAGERY_FAMILIES["金"]


def test_family_assignment_on_real_chars(engine, table_female):
    """真实字的族归属：「秋」在草木（部首禾），不在日月星辰。"""
    by_char = {c["char"]: c for c in table_female["chars"]}
    if "秋" in by_char:
        assert by_char["秋"]["family"] == "草木"
    if "月" in by_char:
        assert by_char["月"]["family"] == "日月星辰"


def test_imagery_families_only_reorders(engine, table_female):
    """意象族**不作硬过滤**：选了草木，表里仍应有非草木的字。

    实测 7 族仅覆盖池内约 35%（金族全池仅 4 字），硬过滤会砍掉 65% 的好字
    （诗/思/安/宜 这类无族属字）。
    """
    picked = engine.pickable_chars(
        surname="林", gender="female", imagery_families=["草木"]
    )
    assert {c["char"] for c in picked["chars"]} == {
        c["char"] for c in table_female["chars"]
    }, "意象族改变了可选字集合——应只影响排序"
    assert picked["no_family"] > 0, "无族属的字不该被砍掉"
    assert {c["char"] for c in picked["chars"][:5]} <= {
        c["char"] for c in picked["chars"] if c["family"] == "草木"
    }, "选中的意象族应排在最前"


def test_families_summary_matches_rows(table_female):
    """族概览的 count 必须等于字表里该族的行数，且顺序固定。"""
    counts = {}
    for row in table_female["chars"]:
        if row["family"]:
            counts[row["family"]] = counts.get(row["family"], 0) + 1
    assert [f["family"] for f in table_female["families"]] == list(IMAGERY_FAMILY_PRIORITY)
    for f in table_female["families"]:
        assert f["count"] == counts.get(f["family"], 0), f"{f['family']} 计数不符"
    assert table_female["no_family"] == sum(
        1 for r in table_female["chars"] if not r["family"]
    )


# ── 硬约束透传 ──

def test_avoid_chars_removed_from_table(engine, table_female):
    """避讳字必须从字表里消失（硬过滤），且不出现在任何示例名里。"""
    top = table_female["chars"][0]["char"]
    picked = engine.pickable_chars(surname="林", gender="female", avoid_chars=[top])
    assert top not in {c["char"] for c in picked["chars"]}
    assert all(top not in n for c in picked["chars"] for n in c["sample"])


def test_source_classes_restrict_supply(engine):
    """先出处限定：只给诗经时，字表里的示例名都应来自诗经。"""
    picked = engine.pickable_chars(
        surname="林", gender="female", source_classes=["诗经"]
    )
    assert picked["chars"], "限定诗经后不该空表"
    sources = set()
    for row in picked["chars"][:8]:
        for name in row["sample"][:1]:
            entry = engine._pair_entry(name[0], name[1], "female", {"诗经"})
            if entry:
                sources.add(entry["source"])
    assert sources <= {"诗经"}, f"限定诗经后仍挂到别的出处：{sources}"


def test_single_char_names_use_single_char_gate(engine):
    """单字名没有「搭档」概念：只问该字本身过不过门槛。

    判据不是「搭档数为 0」（搭档数是字对层面的真实信息，与名字字数无关），
    而是「**零搭档的字也能入选**」——双字口径下这类字必然被排除。
    """
    one = engine.pickable_chars(surname="李", gender="female", name_length=1)
    two = engine.pickable_chars(surname="李", gender="female", name_length=2)
    double = {r["char"] for r in two["chars"]}
    lonely = {r["char"] for r in one["chars"] if r["partner_count"] == 0}
    assert one["feasible"] > two["feasible"], "单字口径可用字应多于双字"
    assert lonely, "单字模式下应有零搭档的字入选"
    assert lonely - double, (
        "应存在「只靠单字口径才可选」的零搭档字——否则单字门槛没起作用"
    )
    assert all(len(r["sample"]) == 1 and r["sample"][0] == r["char"]
               for r in one["chars"])


def test_generational_char_contract(engine):
    """字辈模式：辈字固定第二字，字表里每个字 + 辈字都能真的出名字。

    字辈组合不是诗词字对（「张志远」≠「婵娟」），只要求「第一个字有出处 +
    整名过门槛」，故字表 = 与辈字能组成合格名字的第一个字；辈字本身不入表。
    """
    gen = "志"
    table = engine.pickable_chars(
        surname="李", gender="male", use_bazi=False,
        name_length=2, generational_char=gen,
    )
    assert table["feasible"] > 0, "常见辈字「志」应有可选字"
    assert gen not in {c["char"] for c in table["chars"]}, "辈字本身不应进可选字表"

    # 表内抽 10 字：每个都能出名字，且名字都辈字收尾
    inside = [c["char"] for c in table["chars"]][:10]
    for ch in inside:
        r = engine.generate_names(
            surname="李", gender="male", name_length=2, max_results=20,
            use_bazi=False, selected_chars=[ch], generational_char=gen,
        )
        assert r["total"] > 0, f"表内字 {ch} 配辈字「{gen}」出不来名字"
        assert all(n["given_name"].endswith(gen) for n in r["names"]), (
            f"字辈名未固定第二字：{[n['given_name'] for n in r['names']]}"
        )

    # 直接生成：所有名字辈字收尾
    r = engine.generate_names(
        surname="李", gender="male", name_length=2, max_results=30,
        use_bazi=False, generational_char=gen,
    )
    assert r["total"] > 0
    assert all(n["given_name"].endswith(gen) for n in r["names"])


# ── 诊断脚本委托（防止两套实现漂移） ──

def test_diag_script_delegates_to_engine(engine):
    """scripts/diag_selected_chars.build_feasibility 必须与引擎同源。"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import diag_selected_chars as diag

    feas, dead = diag.build_feasibility(engine, "林", "female")
    table = engine.pickable_chars(surname="林", gender="female")
    assert set(feas) == {c["char"] for c in table["chars"]}
    assert not (set(feas) & set(dead))
    assert len(feas) + len(dead) == table["feasible"] + len(dead)
