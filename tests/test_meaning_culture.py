"""
期许文化记号（app/core/meaning_culture.py）与期许生效程度。

═══ 这个测试守的是什么 ═══

真机反馈：「偏好和气质选择，对最后的名字影响，看不出来有太大区别」，
举例是「期望孩子健康，推荐的名字如何体现」。

复核属实，而且原因不在权重：**「健康」在中文名字里几乎不靠字义直说**
（没人叫「张健康」），而是取松柏后凋、鹤寿千岁这类文化符号；
而原实现拿 `MEANING_OPTIONS["health"]["keywords"]` 去 `chars.meaning` 里找子串，
字库里 87% 的字释义为空（「康」就是空的），「松柏」二字连用的命中数是 0。

所以新增了「文化记号」这一层：字 → 它为什么能代表这个愿望。
引擎据此占硬名额（CULTURE_QUOTA_RATIO），前端据此显示「为什么是松」。

本文件钉住四件事：
1. 字表本身干净：每个期许至少 8 字、字都在候选池里、note 不悬空；
2. 期许真的生效：选了之后至少三成名字带契合点，不选时一个都没有；
3. 不同期许给的是**不同的字族**（不是同一批名字换个顺序）；
4. 契合点是可解释的文案（有字、有期许 code、有人话），不是空壳。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.core.meaning_culture import (
    CHAR_VIRTUE_NOTES,
    MEANING_CULTURE_CHARS,
    culture_chars_for,
    culture_hits,
)
from app.core.naming_options import MEANING_OPTIONS
from app.services.naming_engine import NamingEngine

POETRY_DIR = PROJECT_ROOT / "data" / "poetry"

# 四组典型输入：男女各两例、跨年代，避免只用一组数据得出结论
CASES = [
    dict(surname="林", gender="male", year=1990, month=5, day=20, hour=12),
    dict(surname="李", gender="female", year=1992, month=3, day=8, hour=9),
    dict(surname="王", gender="male", year=1988, month=11, day=1, hour=6),
    dict(surname="陈", gender="female", year=1995, month=7, day=22, hour=15),
]


@pytest.fixture(scope="module")
def candidate_pool() -> set:
    """语料里全部 recommend_chars —— 也就是「理论上能组成名字的字」。"""
    files = ["poetry.json"] + [f"poetry_extra{i}.json" for i in ["", "2", "3", "4", "5"]]
    poems: list = []
    for name in files:
        path = POETRY_DIR / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        poems += (data.get("poems") if isinstance(data, dict) else data) or []
    return {c for p in poems for c in (p.get("recommend_chars") or [])}


@pytest.fixture(scope="module")
def engine() -> NamingEngine:
    return NamingEngine()


# --------------------------------------------------------------------------- #
# 1. 字表本身
# --------------------------------------------------------------------------- #

def test_every_meaning_has_enough_culture_chars():
    """每个期许至少 8 个字：少于这个数，硬名额取不满，效果等于没有"""
    thin = {
        code: len(chars)
        for code, chars in MEANING_CULTURE_CHARS.items()
        if len(chars) < 8
    }
    assert not thin, f"这些期许的文化字太少：{thin}"


def test_culture_chars_cover_all_meanings():
    """14 个期许一个都不能漏 —— 漏了就等于用户选它时系统装没看见"""
    missing = set(MEANING_OPTIONS) - set(MEANING_CULTURE_CHARS)
    assert not missing, f"这些期许没有文化字表：{missing}"
    unknown = set(MEANING_CULTURE_CHARS) - set(MEANING_OPTIONS)
    assert not unknown, f"出现了不存在的期许 code：{unknown}"


def test_culture_chars_are_in_candidate_pool(candidate_pool):
    """
    字表里的字必须真的在语料里。

    否则就是空头支票：用户选了「健康长寿」，看到理由是「松柏长青」，
    可引擎根本组不出带松的名字 —— 本文件顶部注释承诺过这件事，这里守住。
    """
    offenders: dict[str, str] = {}
    for code, chars in MEANING_CULTURE_CHARS.items():
        outside = [c for c in chars if c not in candidate_pool]
        if outside:
            offenders[code] = "".join(outside)
    assert not offenders, f"这些字不在语料候选池里：{offenders}"


def test_culture_chars_are_usable_not_blacklisted():
    """
    字表里不许有「引擎永远不会用」的字（凶字 ∪ blacklist.json）。

    「在 recommend_chars 里」还不够：语料可以推荐它，但 R3 会在组名前拦下。
    留在表里只会让契合点多一条永远不触发的规则 ——
    这次抓到两处：tranquil 含「虚」（黑名单）、resilient 含「寒」（luck=凶）。
    """
    from poetry_utils import load_blacklist

    bad = load_blacklist()
    offenders = {
        code: "".join(c for c in chars if c in bad)
        for code, chars in MEANING_CULTURE_CHARS.items()
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, (
        f"这些期许字表的字永远不会出现在名字里（凶字/黑名单）：{offenders}"
    )


def test_notes_are_attached_to_real_chars():
    """note 表不许有悬空条目（写了理由但没挂进任何期许，就永远不会显示）"""
    attached = set(MEANING_CULTURE_CHARS["health"])  # 起手，逐期许并集
    for chars in MEANING_CULTURE_CHARS.values():
        attached |= set(chars)
    orphans = [ch for ch in CHAR_VIRTUE_NOTES if ch not in attached]
    assert not orphans, f"这些字有 note 但不在任何期许字表里：{orphans}"


def test_notes_say_why_not_whether():
    """
    note 只解释「为什么」，不做吉凶判断。

    这一条与孕期页的合规收敛是同一套口径：不预测、不建议。
    文化出处可以说，好坏不许说。
    """
    banned = ("吉凶", "大吉", "必", "一定", "旺", "克", "凶", "推荐", "最好")
    offenders = {
        ch: note for ch, note in CHAR_VIRTUE_NOTES.items()
        if any(b in note for b in banned)
    }
    assert not offenders, f"这些 note 带了判断性用语：{offenders}"


def test_culture_hits_shape():
    """契合点的结构：字 + 期许 code + 理由，一个字可对应多个期许"""
    hits = culture_hits(["松", "茂"], ["health", "resilient"])
    assert [h["char"] for h in hits] == ["松", "茂"]
    assert hits[0]["codes"] == ["health", "resilient"]   # 松：长寿 + 后凋
    assert hits[0]["note"]                       # 有理由
    assert hits[1]["codes"] == ["health"]
    # 没选期许 / 字不在表内 → 空表
    assert culture_hits(["松"], None) == []
    assert culture_hits(["江"], ["health"]) == []


def test_culture_chars_for_unions_meanings():
    both = culture_chars_for(["health", "beauty"])
    assert "松" in both and "玉" in both
    assert culture_chars_for(None) == set()


# --------------------------------------------------------------------------- #
# 2. 期许真的生效
# --------------------------------------------------------------------------- #

def _fit_rate(engine: NamingEngine, code: str) -> float:
    """四组输入各取 6 个，统计带契合点的比例"""
    total = hit = 0
    for case in CASES:
        names = engine.generate_names(
            **case, name_length=2, max_results=6, meanings=[code]
        )["names"]
        total += len(names)
        hit += sum(1 for n in names if n.get("meaning_fit"))
    return hit / total if total else 0.0


@pytest.mark.parametrize("code", sorted(MEANING_OPTIONS))
def test_meaning_actually_shows_up(engine, code):
    """
    选了期许，至少三成名字要带契合点。

    改前的基线：选「健康长寿」与不选，Top6 里健康相关字只从 0 个变 2 个，
    40 个候选里也只从 6 个变 8 个 —— 用户看不出差别是必然的。
    现在靠 CULTURE_QUOTA_RATIO 硬名额，实测 38%~67%，取 30% 作下限。
    """
    rate = _fit_rate(engine, code)
    assert rate >= 0.3, (
        f"「{MEANING_OPTIONS[code]['name']}」只有 {rate:.0%} 的名字带契合点，"
        f"低于 30% —— 用户会再次觉得「选了什么都没变化」"
    )


def test_no_meaning_means_no_fit(engine):
    """不选期许时不许凭空冒出契合点（否则「契合」二字就没有信息量了）"""
    for case in CASES:
        names = engine.generate_names(**case, name_length=2, max_results=6)["names"]
        assert all(not n.get("meaning_fit") for n in names)


def test_different_meanings_give_different_char_families(engine):
    """
    不同期许要给**不同的字族**，而不是同一批名字换个顺序。

    「健康长寿」应该出松/鹤/柏/康，「俊美清雅」应该出玉/莹/姝/清 ——
    这样用户一眼能看出两者的区别，而不是「换了一批但还是这类名字」。
    """
    def chars_for(code: str) -> set:
        out = set()
        for case in CASES:
            names = engine.generate_names(
                **case, name_length=2, max_results=6, meanings=[code]
            )["names"]
            for n in names:
                out |= {f["char"] for f in (n.get("meaning_fit") or [])}
        return out

    health = chars_for("health")
    beauty = chars_for("beauty")
    assert health and beauty
    overlap = health & beauty
    # 允许共用极少数字（「玉」既主贵也主美），但不能是同一批
    assert len(overlap) <= 2, (
        f"「健康」与「俊美」的契合字重合太多：{overlap}，说明字族没分开"
    )
    assert {"松", "鹤", "柏", "康", "寿", "宁", "安"} & health, (
        f"健康类的契合字里没有任何「长青 / 康宁」字：{health}"
    )


# --------------------------------------------------------------------------- #
# 3. 接口层
# --------------------------------------------------------------------------- #

def test_route_exposes_meaning_fit():
    """契合点必须能被前端拿到（schema 漏字段时会被静默剥掉，这里守住）"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/v1/generate", json={
        "surname": "林", "gender": "male",
        "year": 1990, "month": 5, "day": 20, "hour": 12,
        "name_length": 2, "max_results": 6,
        "meanings": ["health"], "shuffle": False,
    })
    assert resp.status_code == 200
    names = resp.json()["names"]
    assert "meaning_fit" in names[0], "响应里没有 meaning_fit 字段"
    fits = [f for n in names for f in n["meaning_fit"]]
    assert fits, "一个契合点都没有，前端无从解释"
    for f in fits:
        assert f["char"] and f["codes"] and f["note"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
