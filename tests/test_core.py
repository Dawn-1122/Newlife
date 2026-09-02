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


# ── 韵味评分回归 ──

def test_yunwei_surname_coherence_15_gap():
    """韵味评分：杜若配杜 vs 配张，S 姓氏协调维度差 15 分（S1 成词成典 + S2 字义呼应）"""
    engine = NamingEngine()
    duruo_entry = None
    for e in engine.source_db.get_all():
        if e["title"] == "杜若":
            duruo_entry = e
            break
    assert duruo_entry is not None

    ruo = engine.char_db.get_char("若")
    s_du = engine.yunwei.score("杜", [ruo], duruo_entry)
    s_zhang = engine.yunwei.score("张", [ruo], duruo_entry)

    # 姓杜：S1=10（杜若为 text 连续子串）+ S2=5（草木↔香草 呼应）= 15
    assert s_du["surname_coherence"]["s1"] == 10
    assert s_du["surname_coherence"]["s2"] == 5
    assert s_du["surname_coherence"]["total"] == 15
    # 姓张：无成词成典、无字义呼应
    assert s_zhang["surname_coherence"]["total"] == 0
    # 名部分完全相同，唯一差异是 S 的 15 分
    assert s_du["total"] - s_zhang["total"] == 15
    # 名部分各维度一致
    for key in ("provenance", "imagery", "aftertaste", "coherence"):
        assert s_du[key] == s_zhang[key]


def test_yunwei_full_dimension_range():
    """韵味五维分数均在合法区间内且可解释"""
    engine = NamingEngine()
    ruo = engine.char_db.get_char("若")
    duruo_entry = None
    for e in engine.source_db.get_all():
        if e["title"] == "杜若":
            duruo_entry = e
            break
    detail = engine.yunwei.score("杜", [ruo], duruo_entry)
    assert 0 <= detail["provenance"] <= 35
    assert 0 <= detail["imagery"] <= 25
    assert 0 <= detail["aftertaste"] <= 15
    assert 0 <= detail["coherence"] <= 10
    assert 0 <= detail["surname_coherence"]["total"] <= 15
    assert detail["total"] == sum([
        detail["provenance"], detail["imagery"], detail["aftertaste"],
        detail["coherence"], detail["surname_coherence"]["total"],
    ])


def test_generate_returns_yunwei_fields():
    """/generate 返回 scores.yunwei + yunwei_detail，overall 平滑过渡为韵味分"""
    engine = NamingEngine()
    result = engine.generate_names(
        surname="杜",
        gender="female",
        name_length=1,
        max_results=10,
        use_bazi=False,
    )
    assert result["total"] > 0
    for name in result["names"]:
        assert "yunwei" in name["scores"]
        assert "yunwei_detail" in name["scores"]
        assert name["scores"]["overall"] == name["scores"]["yunwei"]
        assert "surname_coherence" in name["scores"]["yunwei_detail"]


def test_source_entries_in_provenance():
    """字源扩展实测：_match_provenance 统一返回诗词 + 字源条目"""
    engine = NamingEngine()
    matches = engine._match_provenance(
        None, "female", None, None, None, use_poetry=True
    )
    entries = [e for e, _tier in matches]
    sources = {e["source"] for e in entries}
    titles = {e["title"] for e in entries}
    # 字源（本草纲目/周易/山海经）与诗词（诗经/楚辞等）并存
    assert "本草纲目" in sources
    assert "周易" in sources
    assert "诗经" in sources
    # 杜若字源条目被纳入统一出处
    assert "杜若" in titles


# ── 漏斗门槛回归 ──

def test_gate_cacophonous():
    """音律门槛：全平/全仄（三字名）或 score<55 硬排除；二字名不因平仄同调排除"""
    assert PhoneticsScorer.is_cacophonous({"rhythm": "平平平", "score": 85}) is True
    assert PhoneticsScorer.is_cacophonous({"rhythm": "仄仄仄", "score": 90}) is True
    assert PhoneticsScorer.is_cacophonous({"rhythm": "平仄平", "score": 40}) is True
    assert PhoneticsScorer.is_cacophonous({"rhythm": "平仄平", "score": 85}) is False
    # 二字名「仄仄」（如杜若）不因平仄同调硬排
    assert PhoneticsScorer.is_cacophonous({"rhythm": "仄仄", "score": 67}) is False
    assert PhoneticsScorer.is_cacophonous({"rhythm": "平平", "score": 80}) is False


def test_gate_wuge_bad():
    """五格门槛：人格+总格双凶才硬排除，单凶放行"""
    assert WugeScorer.is_bad({"ren_ge": {"luck": "凶"}, "zong_ge": {"luck": "凶"}}) is True
    assert WugeScorer.is_bad({"ren_ge": {"luck": "凶"}, "zong_ge": {"luck": "吉"}}) is False
    assert WugeScorer.is_bad({"ren_ge": {"luck": "大吉"}, "zong_ge": {"luck": "凶"}}) is False
    assert WugeScorer.is_bad({"ren_ge": {"luck": "吉"}, "zong_ge": {"luck": "吉"}}) is False


def test_gate_bazi_ji_conflict():
    """八字门槛：名字所有字五行都落在忌神才硬排除"""
    assert BaziEngine.is_ji_wuxing_conflict(["水", "水"], ["水", "火"]) is True
    assert BaziEngine.is_ji_wuxing_conflict(["水"], ["水"]) is True
    assert BaziEngine.is_ji_wuxing_conflict(["水", "木"], ["水", "火"]) is False
    assert BaziEngine.is_ji_wuxing_conflict([], ["水"]) is False
    assert BaziEngine.is_ji_wuxing_conflict(["水"], []) is False


# ── LLM 寓意懒加载回归 ──

def test_name_meaning_fallback_to_template(monkeypatch, tmp_path):
    """/name/meaning：LLM 失败回退模板 + meaning_source=template"""
    import asyncio
    from app.services.llm_service import LLMError

    async def fake_generate_meaning(*args, **kwargs):
        return {
            "error": "mock fail",
            "meaning": "",
            "poetry_note": "",
            "wuxing_note": "",
            "overall_note": "",
        }

    engine = NamingEngine()
    # 隔离缓存目录，避免污染真实 data/meaning_cache
    monkeypatch.setattr(engine.cache, "_cache_dir", tmp_path)
    engine.cache.clear()
    monkeypatch.setattr(engine.llm, "generate_meaning", fake_generate_meaning)
    result = asyncio.run(engine.generate_meaning_detail("杜若", "female"))
    assert result["meaning_source"] == "template"
    assert result["full_name"] == "杜若"
    assert result["layers"]
    assert result["meaning"]


def test_name_meaning_llm_success_path(monkeypatch, tmp_path):
    """/name/meaning：LLM 成功返回多层 layers + meaning_source=llm"""
    import asyncio

    async def fake_generate_meaning(*args, **kwargs):
        return {
            "layers": [
                {"level": "字面", "text": "第一层"},
                {"level": "出处", "text": "第二层"},
                {"level": "余味", "text": "第三层"},
            ],
            "meaning": "整体解读",
            "poetry_note": "出处意境",
            "wuxing_note": "五行分析",
            "overall_note": "点睛",
            "provider": "deepseek",
            "model": "deepseek-chat",
        }

    engine = NamingEngine()
    monkeypatch.setattr(engine.cache, "_cache_dir", tmp_path)
    engine.cache.clear()
    monkeypatch.setattr(engine.llm, "generate_meaning", fake_generate_meaning)
    result = asyncio.run(engine.generate_meaning_detail("徐长卿", "male"))
    assert result["meaning_source"] == "llm"
    assert len(result["layers"]) == 3
    assert result["meaning"] == "整体解读"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
