"""「换一批」排除名单（exclude_names）。

背景：后端无固定 seed，「换一批」原先是重新掷骰子。高分池只有二三十个字对，
连翻两批必然把同一批名字抽回来——实测顾/男 elegant 三批里「清浅/素秋/清秋」
各出现三次。前端把已展示名字回传，后端硬剔除，这一组测试守的就是这条契约：

1. 传了就一定不出现在结果里（硬约束，不是加权）；
2. 连翻多批不重复（前端的真实用法）；
3. 池子翻完时返回空 + 说明，不能悄悄回退到已排除的名字；
4. 接口层收得下这个字段，且不影响不带排除名单的老请求。
"""

import pytest

from app.services.naming_engine import NamingEngine


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


def _gen(engine, **kw):
    params = dict(
        surname="顾", gender="male", name_length=2,
        max_results=6, use_bazi=False, style="elegant",
    )
    params.update(kw)
    return engine.generate_names(**params)


def test_excluded_names_never_come_back(engine):
    """第一遍拿到的名字，作为排除名单传回去，第二遍一个都不能有。"""
    first = _gen(engine)
    taken = [n["given_name"] for n in first["names"]]
    assert taken, "前置条件：第一批应有结果"

    for _ in range(3):
        again = _gen(engine, exclude_names=taken)
        overlap = set(taken) & {n["given_name"] for n in again["names"]}
        assert not overlap, f"排除名单失效：{overlap}"


def test_refresh_batches_never_repeat(engine):
    """模拟前端连翻 5 批：累计排除，五批合起来必须互不重复。"""
    seen: list[str] = []
    for _ in range(5):
        r = _gen(engine, exclude_names=seen)
        got = [n["given_name"] for n in r["names"]]
        assert not (set(got) & set(seen)), "换一批出现了已展示过的名字"
        seen.extend(got)
    assert len(seen) == len(set(seen))
    # 五批仍应翻得出东西（否则「排除」变成了「清空」）
    assert len(seen) >= 12, f"连翻 5 批只出 {len(seen)} 个，供给不足"


def test_emptied_pool_returns_note_not_repeats(engine):
    """把池子翻空：宁可返回空 + 说明，也不能回退去给已排除的名字。"""
    seen: list[str] = []
    r = None
    for _ in range(30):
        r = _gen(engine, exclude_names=seen)
        got = [n["given_name"] for n in r["names"]]
        assert not (set(got) & set(seen))
        if not got:
            break
        seen.extend(got)

    assert not r["names"], "翻到第 30 批仍有结果，说明池子比预期大（测试前提变了）"
    assert r["fallback_note"], "掏空时应给出说明，不能静默返回空列表"


def test_without_exclusion_behaviour_unchanged(engine):
    """不带排除名单时行为不变：仍能返回 6 个，且没有多出空结果说明。"""
    r = _gen(engine)
    assert len(r["names"]) == 6
    assert r["fallback_note"] is None


def test_exclusion_survives_gender_and_name_length(engine):
    """单字名与女性向也要生效（排除名单走的是同一层，不分性别/字数）。"""
    for kw in (dict(gender="female", style=None), dict(name_length=1, style=None)):
        first = _gen(engine, **kw)
        taken = [n["given_name"] for n in first["names"]]
        if not taken:
            continue
        again = _gen(engine, exclude_names=taken, **kw)
        assert not (set(taken) & {n["given_name"] for n in again["names"]})


def test_route_accepts_exclude_names():
    """/generate 收得下 exclude_names，且结果里不含被排除的名字。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    body = {
        "surname": "沈", "gender": "female", "name_length": 2,
        "max_results": 4, "use_bazi": False,
    }
    first = client.post("/api/v1/generate", json=body)
    assert first.status_code == 200
    taken = [n["given_name"] for n in first.json()["names"]]
    assert taken

    second = client.post(
        "/api/v1/generate", json={**body, "exclude_names": taken}
    )
    assert second.status_code == 200
    assert not (set(taken) & {n["given_name"] for n in second.json()["names"]})
