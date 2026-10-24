"""出处候选的去重口径，以及排除名单的收口位置。

两个都属「静默」类缺陷，出错时不报错、只是结果变少或变重复：

1. **去重键**：`_match_sources` 与 `_available_source_entries` 原按
   `(source, title)` 去重。但一个篇目本来就该贡献多个短句单元——《离骚》14 条、
   《浣溪沙》57 条、《水调歌头》12 条，各挂各的推荐字与字对。按篇名去重把它们
   当重复整条丢弃，全库 1233 条里 654 条（53%）从未进入候选。这也解释了
   「五代词出不了名字」：57 首浣溪沙只剩 1 首可出，不是语料性质问题。

2. **排除名单的收口**：`exclude_names` 原先在 `_compose_names` 返回后过滤，
   候选池还要按排除量放大（`pool_size = max_results + len(skip)`）。实测
   exclude=120 时延迟从 109ms 涨到 893ms。改为在 `emit()`（所有产出路径的唯一
   出口）剔除、池子不放大后，延迟与名单长度无关。
"""

import pytest

from app.services.naming_engine import NamingEngine


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


def test_entry_key_uses_id_not_title(engine):
    """同篇不同句是不同条目，去重键必须区分开。"""
    a = {"id": "poem_1", "source": "楚辞", "title": "离骚"}
    b = {"id": "poem_2", "source": "楚辞", "title": "离骚"}
    assert engine._entry_key(a) != engine._entry_key(b)
    assert engine._entry_key(a) == engine._entry_key(dict(a))


def test_same_title_entries_all_reach_candidates(engine):
    """《浣溪沙》不该只剩一条能进候选——这是 53% 条目消失的直接观测点。"""
    matches = engine._match_provenance(
        gender="male", blacklist=set(),
        use_poetry=True, source_classes=["五代词"],
    )
    titles = [e.get("title") for e, _ in matches]
    assert titles.count("浣溪沙") > 1, (
        f"浣溪沙只剩 {titles.count('浣溪沙')} 条进候选，去重键疑回退到篇名"
    )
    assert len(titles) == len(set(
        e.get("id") for e, _ in matches
    )), "候选里有重复条目（同一条目被收了两次）"


def test_candidates_not_silently_dropped(engine):
    """可用条目数应等于库里「本类目 + 有推荐字 + 非哀伤」的条目数。"""
    wanted = "楚辞"
    available = [
        e for e in engine.poetry_db.get_by_gender("male")
        if e.get("source") == wanted
        and e.get("recommend_chars")
        and not NamingEngine._is_sad_poem(e)
    ]
    matches = engine._match_provenance(
        gender="male", blacklist=set(),
        use_poetry=True, source_classes=[wanted],
    )
    assert len(matches) == len(available), (
        f"候选 {len(matches)} 条 vs 库内可用 {len(available)} 条——有条目被静默丢弃"
    )


def test_exclusion_applies_to_single_char_path(engine):
    """单字名走的是另一条组合路径，排除名单同样要生效。"""
    first = engine.generate_names(
        surname="林", gender="female", name_length=1,
        max_results=6, use_bazi=False,
    )
    taken = [n["given_name"] for n in first["names"]]
    assert taken
    again = engine.generate_names(
        surname="林", gender="female", name_length=1,
        max_results=6, use_bazi=False, exclude_names=taken,
    )
    assert not (set(taken) & {n["given_name"] for n in again["names"]})


def test_exclusion_applies_to_generational_path(engine):
    """字辈模式（辈字固定第二字）也走 emit，排除名单必须同样生效。"""
    kw = dict(
        surname="张", gender="male", name_length=2, max_results=6,
        use_bazi=False, generational_char="远",
    )
    first = engine.generate_names(**kw)
    taken = [n["given_name"] for n in first["names"]]
    assert taken, "字辈模式应能出名字"
    again = engine.generate_names(**kw, exclude_names=taken)
    assert not (set(taken) & {n["given_name"] for n in again["names"]})
