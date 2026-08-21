"""
核心引擎功能测试（pytest 断言式）

覆盖：
- 八字排盘（年/月/日/时四柱、五行、喜用神）
- 字库、诗词库、音律、五格数理
- 起名完整流程
- P0 修复回归：hour=0 不被吞成午时、23点晚子时跨日、负面字/哀伤诗词过滤
"""

import os
import sys

# 添加项目根目录到 path（兼容未设置 PYTHONPATH 的运行方式）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.core.constants import NEGATIVE_CHARS, SAD_POETRY_TITLES
from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.services.naming_engine import NamingEngine


# ── 八字排盘 ──

def test_bazi_pailan():
    """测试八字排盘核心字段"""
    result = BaziEngine.generate_bazi(2025, 1, 15, 10, 0, "male")

    assert result["solar_date"] == "2025-01-15 10:00"
    assert result["gender"] == "male"
    assert result["day_master"]  # 日主非空
    assert result["day_master"] in result["four_pillars"]["day"]

    pillars = result["four_pillars"]
    assert set(pillars.keys()) == {"year", "month", "day", "hour"}
    for pz in pillars.values():
        assert len(pz) == 2  # 天干+地支

    # 五行分布
    wuxing = result["wuxing"]
    assert set(wuxing["percentages"].keys()) == {"金", "木", "水", "火", "土"}
    assert abs(sum(wuxing["percentages"].values()) - 100.0) < 0.5

    # 喜用神
    assert result["xiyong"]["day_master"] == result["day_master"]
    assert result["xiyong"]["strength_label"] in ("身强", "身弱")
    assert result["xiyong"]["xi_wuxing"]


# ── 字库 ──

def test_char_db():
    """测试字库查询"""
    db = CharDatabase()
    assert db.total > 0

    jin_chars = db.get_by_wuxing("金", "male")
    assert len(jin_chars) > 0
    assert all(c["wuxing"] == "金" for c in jin_chars)

    info = db.get_char("明")
    assert info is not None
    assert info["char"] == "明"
    assert info["wuxing"]
    assert info["kangxi_strokes"] > 0


# ── 诗词库 ──

def test_poetry_db():
    """测试诗词库查询"""
    db = PoetryDatabase()
    assert db.total > 0

    poems = db.get_by_char("明")
    assert len(poems) > 0
    assert all("明" in p["recommend_chars"] for p in poems)


# ── 音律评分 ──

def test_phonetics():
    """测试音律评分"""
    for name in ["张伟", "李清照", "王子轩"]:
        result = PhoneticsScorer.analyze(name)
        assert result["pinyins"]
        assert len(result["tones"]) == len(name)
        assert 0 <= result["score"] <= 100


# ── 五格数理 ──

def test_wuge():
    """测试五格数理"""
    for surname, given in [("张", "伟"), ("李", "清照"), ("王", "子轩")]:
        result = WugeScorer.calculate(surname, given)
        for key in ("tian_ge", "ren_ge", "di_ge", "wai_ge", "zong_ge"):
            assert key in result
            assert "value" in result[key]
        assert 0 <= result["total_score"] <= 100


# ── 起名完整流程 ──

def test_naming_engine_full_flow():
    """测试起名引擎完整流程（带八字）"""
    engine = NamingEngine()
    result = engine.generate_names(
        surname="张",
        gender="male",
        year=2025,
        month=1,
        day=15,
        hour=10,
        minute=0,
        name_length=2,
        max_results=5,
    )

    assert result["total"] > 0
    assert len(result["names"]) == result["total"]
    assert result["bazi"] is not None
    assert result["bazi"]["four_pillars"]["day"]

    for name in result["names"]:
        assert name["full_name"].startswith("张")
        assert name["given_name"]
        assert name["phonetics"]["score"] >= 0
        assert "overall" in name["scores"]
        assert name["meaning"]


def test_naming_engine_without_bazi():
    """测试起名引擎不带八字"""
    engine = NamingEngine()
    result = engine.generate_names(
        surname="李",
        gender="female",
        name_length=2,
        max_results=3,
        use_bazi=False,
    )
    assert result["bazi"] is None
    assert result["total"] > 0


# ── P0 修复回归 ──

def test_hour_zero_is_zi_shi():
    """P0：hour=0 时应为子时，不能被 `or 12` 吞成午时"""
    result = BaziEngine.generate_bazi(2025, 1, 15, 0, 0, "male")
    assert result["four_pillars"]["hour"].endswith("子")


def test_hour_zero_via_route():
    """P0：/generate 接口 hour=0 时柱应为子时"""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/generate",
        json={
            "surname": "张",
            "gender": "male",
            "year": 2025,
            "month": 1,
            "day": 15,
            "hour": 0,
            "minute": 0,
            "name_length": 2,
            "max_results": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bazi"]["four_pillars"]["hour"].endswith("子")


def test_late_zi_shi_crosses_day():
    """P0：23点晚子时按次日排盘——2025-01-15 23:00 日柱应为次日乙酉"""
    result = BaziEngine.generate_bazi(2025, 1, 15, 23, 0, "male")
    assert result["four_pillars"]["day"] == "乙酉"
    # 时支仍为子时
    assert result["four_pillars"]["hour"].endswith("子")


def test_negative_chars_filtered():
    """P0：负面字过滤——姓张男 2025-01-15 10:00 生成结果不含『匪』字"""
    engine = NamingEngine()
    result = engine.generate_names(
        surname="张",
        gender="male",
        year=2025,
        month=1,
        day=15,
        hour=10,
        minute=0,
        name_length=2,
        max_results=30,
    )

    all_names = "".join(n["full_name"] for n in result["names"])
    assert "匪" not in all_names
    # 更严格：任何黑名单字都不应出现在结果中
    for bad in NEGATIVE_CHARS:
        assert bad not in all_names, f"负面字『{bad}』出现在生成结果中"


def test_sad_poetry_filtered():
    """P0：哀伤类诗词过滤——生成结果不引用哀伤类诗词出处"""
    engine = NamingEngine()
    result = engine.generate_names(
        surname="张",
        gender="male",
        year=2025,
        month=1,
        day=15,
        hour=10,
        minute=0,
        name_length=2,
        max_results=30,
    )

    for name in result["names"]:
        poetry = name.get("poetry")
        if poetry:
            title = poetry.get("title", "")
            assert not any(sad in title for sad in SAD_POETRY_TITLES), (
                f"哀伤类诗词『{title}』出现在出处中"
            )


def test_poem_chars_blacklist_filtered():
    """P0：同源组名的推荐字应过滤负面字（淇奥中的『匪』应被排除）"""
    engine = NamingEngine()
    poem = engine.poetry_db.get_by_char("匪")[0]
    valid = engine._get_valid_poem_chars(poem, "male", None)
    valid_chars = {c["char"] for c in valid}
    assert "匪" not in valid_chars
    # 同一首诗的其他正面字仍应保留
    assert "淇" in valid_chars or "竹" in valid_chars


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
