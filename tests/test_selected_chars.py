"""
先字（selected_chars）/ 先出处（source_classes）契约测试。

先字模式语义 = **名字必须含所选字（任一位置）**，不是「名字只用所选字」——
后者对单个点选字必然 0 结果（一个字无法自成字对），是已废弃的旧语义。

配套人工诊断：scripts/diag_selected_chars.py
（覆盖表 / 门槛感知可行性 / 逐字 live 验证 / 可选字表导出）。
"""

import pytest

from app.services.naming_engine import NamingEngine


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


def test_selected_single_char_must_contain(engine):
    """单字点选：出名字，且每个名字都含该字（回归：旧实现单字必然 0 结果）。"""
    result = engine.generate_names(
        surname="李", gender="female", name_length=2, max_results=30,
        selected_chars=["清"],
    )
    assert result["total"] > 0
    assert all("清" in n["given_name"] for n in result["names"])


def test_selected_multi_chars_any_hit(engine):
    """多字点选：名字含任一所选字即可（不必全部命中）。"""
    result = engine.generate_names(
        surname="李", gender="female", name_length=2, max_results=30,
        selected_chars=["清", "月"],
    )
    assert result["total"] > 0
    for n in result["names"]:
        assert any(ch in {"清", "月"} for ch in n["given_name"]), (
            f"{n['given_name']} 不含任何所选字 —— 先字模式契约被破坏"
        )


def test_selected_double_hit_exists(engine):
    """双命中：「清」与「秋」互为已批准搭档（清秋），选这两个字应出现双双命中的名字。"""
    result = engine.generate_names(
        surname="李", gender="female", name_length=2, max_results=30,
        selected_chars=["清", "秋"],
    )
    assert result["total"] > 0
    double = [n["given_name"] for n in result["names"]
              if "清" in n["given_name"] and "秋" in n["given_name"]]
    assert double, "「清秋」为已批准字对，双命中组合不应缺席"


def test_selected_hits_tiebreak_in_rank(engine):
    """先字命中数是**同分 tie-break**（韵味分仍为主排序键）。

    （最终输出还会经过多样性与分层抽样，故在 _rank_by_yunwei 层面验证排序键。）
    """
    def mk(given, yunwei, hits):
        return {
            "given_name": given,
            "scores": {"yunwei": yunwei},
            "chars_info": [],
            "_selected_hits": hits,
        }

    ranked = engine._rank_by_yunwei(
        [mk("清瑶", 70, 1), mk("清月", 70, 2), mk("月明", 72, 1)],
        None, None, None,
    )
    assert [n["given_name"] for n in ranked] == ["月明", "清月", "清瑶"]


def test_selected_char_without_pairs_explains_itself(engine):
    """无字对覆盖的字：空结果 + 「无搭档」提示（不静默空手）。"""
    result = engine.generate_names(
        surname="李", gender="female", name_length=2, max_results=30,
        selected_chars=["言"],
    )
    assert result["total"] == 0
    assert result["fallback_note"] and "搭档" in result["fallback_note"]


def test_selected_char_blocked_by_surname_explains_itself(engine):
    """有搭档但与姓氏条件组合不出：空结果 + 区分于「无搭档」的提示。

    「诗」仅与「陶」成对（男性条目），对女性、或与「林」姓谐音均受限。
    """
    result = engine.generate_names(
        surname="林", gender="female", name_length=2, max_results=30,
        selected_chars=["诗"],
    )
    assert result["total"] == 0
    note = result["fallback_note"]
    assert note and "搭档" not in note, "应给出「与姓氏条件受限」类提示"


def test_source_classes_filter(engine):
    """先出处：类目限定后，产出名字的出处必须全部落在所选类目内。"""
    result = engine.generate_names(
        surname="林", gender="female", name_length=2, max_results=20,
        source_classes=["诗经"],
    )
    assert result["total"] > 0
    for n in result["names"]:
        poetry = n.get("poetry")
        if poetry:
            assert poetry["source"] == "诗经" or poetry["source_class"] == "诗经", (
                f"{n['given_name']} 挂到了 {poetry['source']} —— 先出处契约被破坏"
            )


def test_source_classes_jing_shi_zi_ji_covers_source_db(engine):
    """「经史子集」应同时覆盖诗词库该类目与字源 4 部典籍（source_class 同值）。

    不断言「姓林一定出得来」：该类目经名字感闸门后只剩个位数可用字对（其余是
    「仁义/明德/笃志」这类训诫词，不宜作名），姓氏三连同调一挡就可能全灭。
    故改为多姓氏扫描：**凡有结果就必须同属该类目**，且该类目在整体上是可达的。
    """
    reachable = False
    for surname in ("林", "苏", "顾", "沈"):
        for gender in ("female", "male"):
            result = engine.generate_names(
                surname=surname, gender=gender, name_length=2, max_results=20,
                source_classes=["经史子集"],
            )
            if result["total"]:
                reachable = True
            for n in result["names"]:
                poetry = n.get("poetry")
                if poetry:
                    assert poetry["source_class"] == "经史子集", (
                        f"{n['full_name']} 挂到了 {poetry['source_class']} 的出处"
                    )
    assert reachable, "「经史子集」类目一个名字都出不来 —— 类目映射可能断了"


def test_poetry_carries_original_text(engine):
    """三级溯源：poetry 对象须透出完整原文段落（缺字段时退回 text，不得为空）。"""
    result = engine.generate_names(
        surname="林", gender="female", name_length=2, max_results=20,
    )
    with_poetry = [n for n in result["names"] if n.get("poetry")]
    assert with_poetry, "基准生成应带上出处"
    for n in with_poetry:
        assert n["poetry"].get("original_text"), "original_text 不得为空"
