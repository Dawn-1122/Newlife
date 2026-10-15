"""姓氏结合模块 + 两阶段选字推荐 测试"""

from app.services.surname_fit import SurnameFit
from app.services.naming_engine import NamingEngine


def _fit():
    return SurnameFit()


def test_homophone_taboo_positive():
    fit = _fit()
    assert fit.is_homophone_taboo("杜", "子腾")[0] is True
    assert fit.is_homophone_taboo("吴", "德")[0] is True
    assert fit.is_homophone_taboo("杨", "伟")[0] is True
    assert fit.is_homophone_taboo("毕", "云涛")[0] is True
    assert fit.is_homophone_taboo("史", "珍香")[0] is True


def test_homophone_taboo_prefix():
    fit = _fit()
    # 吴德凯 → wudekai 以 wude 开头
    hit, word = fit.is_homophone_taboo("吴", "德凯")
    assert hit is True
    assert word == "无德"


def test_homophone_taboo_negative():
    fit = _fit()
    assert fit.is_homophone_taboo("张", "伟强")[0] is False
    assert fit.is_homophone_taboo("李", "明轩")[0] is False
    assert fit.is_homophone_taboo("王", "若溪")[0] is False


def test_meaning_conflict():
    fit = _fit()
    assert fit.is_meaning_conflict("朱", "红")[0] is True
    assert fit.is_meaning_conflict("朱", "丹")[0] is True
    assert fit.is_meaning_conflict("白", "云")[0] is True
    assert fit.is_meaning_conflict("朱", "若溪")[0] is False
    assert fit.is_meaning_conflict("李", "云")[0] is False


def test_tri_tone_conflict():
    fit = _fit()
    # 张芳芳 zhang1 fang1 fang1 = 平平平 → 冲突
    assert fit.tri_tone_conflict("张", ["芳", "芳"]) is True
    # 张伟强 zhang1 wei3 qiang2 = 平仄平 → 不冲突
    assert fit.tri_tone_conflict("张", ["伟", "强"]) is False
    # 单字名不判定
    assert fit.tri_tone_conflict("张", ["伟"]) is False


def test_generate_excludes_homophone_taboo():
    engine = NamingEngine()
    result = engine.generate_names(
        surname="杜", gender="male", name_length=2, max_results=50
    )
    for n in result["names"]:
        assert n["full_name"] != "杜子腾"


def test_recommend_chars():
    engine = NamingEngine()
    result = engine.recommend_chars(
        surname="李", gender="female", year=2020, month=5, day=20, limit_per_group=5
    )
    assert result["total"] > 0
    assert result["groups"], "应返回至少一个五行分组"
    # 喜用神分组应排在前面
    assert result["groups"][0]["is_xiyong"] is True
    for g in result["groups"]:
        for c in g["chars"]:
            assert c["wuxing"] == g["wuxing"]


def test_generate_with_selected_chars():
    """先字模式：selected_chars 语义 = 名字必须含所选字（任一位置）。

    注意不是「名字只用所选字」——旧语义对单个字必然 0 结果（一个字无法自成字对），
    已废弃；此处特意混入一个无字对覆盖的字（若）验证其余字仍能出名字。
    """
    engine = NamingEngine()
    result = engine.generate_names(
        surname="李", gender="female", name_length=2, max_results=30,
        selected_chars=["若", "溪", "清"],
    )
    assert result["total"] > 0
    for n in result["names"]:
        assert any(ch in {"若", "溪", "清"} for ch in n["given_name"]), (
            f"{n['given_name']} 不含任何所选字 —— 先字模式契约被破坏"
        )


def test_generate_with_single_selected_char():
    """单个所选字也要出名字（回归：旧实现单字必然 0 结果）。"""
    engine = NamingEngine()
    result = engine.generate_names(
        surname="李", gender="female", name_length=2, max_results=30,
        selected_chars=["清"],
    )
    assert result["total"] > 0, "「清」在语料里覆盖充足，不应空手"
    for n in result["names"]:
        assert "清" in n["given_name"]
