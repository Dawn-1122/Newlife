"""名字感分级（第三道闸）的契约测试。

背景：`name_pairs` 的 671 个字对由 `pair_annotator` + `pair_review` 两道 LLM 闸
审定，取向是「像不像诗里的好词」。用户体感「土」的那一批（明月/春风/银河/翠凤）
恰好都能过那两道闸——它们是诗句里的好词，只是不能写在出生证明上。

第三道闸 `data/poetry/pair_taste.json` 就是补这个缺口：
5=优先 / 4=可用 / 3=兜底 / 1=屏蔽，白名单外默认 1（未定级 = 不出）。
"""

import json
from pathlib import Path

import pytest

from app.services.naming_engine import NamingEngine

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "data" / "poetry" / "name_pairs.json"
TASTE = ROOT / "data" / "poetry" / "pair_taste.json"


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


@pytest.fixture(scope="module")
def taste() -> dict:
    return json.loads(TASTE.read_text(encoding="utf-8"))["scores"]


def test_every_pair_is_graded(taste):
    """语料里每个字对都必须有定级。

    语料扩了而分级没跟上时，新字对会静默变成「屏蔽」——名字变少是可见的，
    但根因不可见。这条测试把它变成显式的红灯：先定级，再上语料。
    """
    pairs = json.loads(PAIRS.read_text(encoding="utf-8"))
    words = {
        p[0] + p[1]
        for ps in pairs.values() for p in ps
        if isinstance(p, list) and len(p) == 2
    }
    missing = sorted(w for w in words if w not in taste)
    assert not missing, f"这些字对没有名字感定级（默认会被屏蔽）：{missing}"


def test_grades_are_in_range(taste):
    assert set(taste.values()) <= {1, 3, 4, 5}, "分级只允许 1/3/4/5（2 分无意义）"
    assert sum(1 for v in taste.values() if v == 5) >= 10, "5 分档不应为空"


def test_banned_pairs_never_appear(engine, taste):
    """屏蔽档（1 分）一个都不许出现在产出里——这是用户「土」的直接来源。"""
    leaked = set()
    for surname, gender, style in (
        ("林", "female", None), ("林", "male", None),
        ("苏", "female", "elegant"), ("江", "male", "bold"),
    ):
        for _ in range(3):
            r = engine.generate_names(
                surname=surname, gender=gender, name_length=2,
                max_results=6, use_bazi=False, style=style,
            )
            for n in r["names"]:
                g = n["given_name"]
                if len(g) == 2 and taste.get(g, 1) <= 1:
                    leaked.add(g)
    assert not leaked, f"屏蔽档字对漏出：{sorted(leaked)}"


def test_good_pairs_dominate(engine, taste):
    """产出应以 4/5 分为主（实测约 62%），不能靠兜底档凑数。"""
    good = total = 0
    for surname, gender in (("林", "female"), ("苏", "male"), ("顾", "female")):
        r = engine.generate_names(
            surname=surname, gender=gender, name_length=2,
            max_results=6, use_bazi=False,
        )
        for n in r["names"]:
            g = n["given_name"]
            if len(g) != 2:
                continue
            total += 1
            if taste.get(g, 1) >= 4:
                good += 1
    assert total, "样本为空，生成链路可能坏了"
    assert good / total >= 0.5, f"优质字对占比过低：{good}/{total}"


def test_reverse_order_is_graded_separately():
    """倒序不继承正序分数（「幽韵」可用 ≠ 「韵幽」可用）。"""
    e = NamingEngine()
    assert e._pair_taste("幽", "韵") >= 3
    assert e._pair_taste("韵", "幽") <= 1


def test_missing_file_degrades_gracefully():
    """分级文件缺失时降级为不分级，而不是让整个引擎哑掉。"""
    e = NamingEngine()
    e.pair_taste = {}
    assert e._pair_taste("春", "风") == 3
    r = e.generate_names(
        surname="林", gender="female", name_length=2,
        max_results=6, use_bazi=False,
    )
    assert r["total"] > 0, "缺分级文件时应退回旧行为，仍能出名字"
