"""先出处模式（source_classes）的空结果说明。

背景：`source_classes=["五代词"]` 实测返回 **0 个名字且 `fallback_note=None`**。
前端 `result.wxml` 只有一个 `wx:if="{{fallbackNote}}"` 的提示条，note 为 None 时
整页就只剩一句「暂无结果」——用户既不知道这类典故本来就少，也不知道该动类目
还是动姓氏。空白本身不会报错，所以能藏很久。

这一组测试守四件事：
1. 空结果必须有说明（不许 None）；
2. 说明要能区分类目本身没材料 / 没适本性别的材料 / 有材料但组不出；
3. 「类目没材料」优先于「换一批翻完了」，否则原因会被误判成翻页翻过头；
4. 有结果的正常请求不许被带上说明。
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.naming_engine import NamingEngine

# 实测最薄的两类：五代词（花间集/南唐词，多为闺阁套语）、清词
THIN_CLASS = "清词"


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


def _gen(engine, **kw):
    params = dict(
        surname="林", gender="male", name_length=2,
        max_results=6, use_bazi=False,
    )
    params.update(kw)
    return engine.generate_names(**params)


def test_empty_class_returns_note_not_silence(engine):
    """类目翻不出名字时，必须带回一句说明（这是 P0 的正题）。"""
    empties = [
        r for r in (_gen(engine, source_classes=[THIN_CLASS], gender=g)
                    for g in ("male", "female"))
        if not r["names"]
    ]
    assert empties, "前置条件：清词在某个性别口径下应当翻不出名字"
    for r in empties:
        assert r["fallback_note"], "空结果却没有任何说明——用户只会看到空白页"
        assert THIN_CLASS in r["fallback_note"], "说明里应点名是哪个类目"


def test_unknown_class_says_not_collected(engine):
    """根本没收录的类目，说法要不一样：这是收录缺口，不是「字句不合用」。"""
    r = _gen(engine, source_classes=["伪典"])
    assert not r["names"]
    assert "还没有收录" in r["fallback_note"]


def test_note_survives_exclude_names(engine):
    """类目没材料 + 排除名单同时存在时，原因应归给类目。

    「换一批」的「翻完了」是翻页翻过头的说法，用在类目空的情况下是误导：
    用户会去反复换一批，而正确动作是换类目。
    """
    r = _gen(engine, source_classes=[THIN_CLASS], gender="male",
             exclude_names=["子墨", "清和"])
    assert not r["names"]
    assert THIN_CLASS in r["fallback_note"], (
        f"原因被误判成「翻完了」：{r['fallback_note']}"
    )


def test_single_char_mode_uses_same_note_path(engine):
    """单字名与双字名共用同一处空结果判断，类目完全没收录时同样有说明。"""
    r = _gen(engine, source_classes=["伪典"], name_length=1)
    assert not r["names"]
    assert "还没有收录" in r["fallback_note"]


def test_thin_classes_still_yield_single_names(engine):
    """实测结论：薄类目在**单字**模式下不会翻空，别给它乱加说明。

    单字只吃单个推荐字，不像双字那样要求「字对成立 + 过名字感闸」，
    故五代词/清词单字仍是 6/6（实测各 3 轮）。P0 的说明只该在真出不了名字时出现。
    """
    for cls in ("五代词", "清词"):
        for gender in ("male", "female"):
            r = _gen(engine, source_classes=[cls], name_length=1, gender=gender)
            assert r["names"], f"{cls}/{gender} 单字名不该为空"
            assert r["fallback_note"] is None, "有结果却带了空结果说明"


def test_normal_class_has_no_note(engine):
    """有结果的请求不许被塞说明——提示条只在真出不了名字时出现。"""
    r = _gen(engine, source_classes=["诗经"])
    assert r["names"], "前置条件：诗经应有结果"
    assert r["fallback_note"] is None


def test_route_surfaces_the_note():
    """/generate 的响应体里要能读到这句说明（前端全靠它）。"""
    client = TestClient(app)
    body = {
        "surname": "林", "gender": "female", "name_length": 2,
        "max_results": 4, "use_bazi": False,
        "source_classes": [THIN_CLASS],
    }
    res = client.post("/api/v1/generate", json=body)
    assert res.status_code == 200
    data = res.json()
    if data["names"]:
        assert data["fallback_note"] is None
    else:
        assert data["fallback_note"], "空结果没有说明，前端只能显示空白"
