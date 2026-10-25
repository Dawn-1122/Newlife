"""
气质字族（app/core/meaning_culture.STYLE_CULTURE_CHARS）与气质生效程度。

═══ 这个测试守的是什么 ═══

真机反馈：「偏好和气质选择，对最后的名字影响，看不出来有太大区别」。
复核属实：8 个气质里 7 个有效，但「古风雅致」**倒挂** ——
选它之后出自诗经/楚辞/汉魏/五代词的比例是 50%，**不选时是 67%**。

原因不在权重，在维度：「古风」按**出处**判定，而整个语料本来就是古典的
（诗经条目最多，这四部典籍占语料六成以上）。硬名额反而把这 3 席让给了唐诗宋词。
更要紧的是用户读不出「诗经还是唐诗」的差别，他能读出来的是
「云、月、苔、石」与「山、河、岳、坤」的差别。

所以气质从「出处维度」改成「字族维度」：
引擎按字族占硬名额（STYLE_FAMILY_RATIO，从偏好配额里扣），
出处降为同层加分（STYLE_SOURCE_BONUS）；前端的向导提示、结果卡、详情页、
结果页筛选条全部改用字族（镜像一致性由 tests/test_frontend_mirror.py 守）。

本文件钉住四件事：
1. 字表本身干净：8 个气质各有 ≥8 字、字都在候选池里、说明不悬空；
2. 气质真的生效：每个气质「选 vs 不选」名字命中率至少差 15pt（实测 41%~68% vs 3%~18%）；
3. 「古风雅致」不许再倒挂 —— 这是本轮改造的回归点；
4. 契合点可解释：命中有字、有气质 code、有说明；不选气质时为空。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.core.meaning_culture import (
    STYLE_CULTURE_CHARS,
    STYLE_CULTURE_NOTES,
    style_culture_chars,
    style_hits,
)
from app.core.naming_options import STYLE_OPTIONS
from app.services.naming_engine import NamingEngine

POETRY_DIR = PROJECT_ROOT / "data" / "poetry"

# 四组典型输入：男女各两例、跨年代 —— 与 test_meaning_culture 同一套，
# 避免「只用一组数据得出结论」。
CASES = [
    dict(surname="林", gender="male", year=1990, month=5, day=20, hour=12),
    dict(surname="李", gender="female", year=1992, month=3, day=8, hour=9),
    dict(surname="王", gender="male", year=1988, month=11, day=1, hour=6),
    dict(surname="陈", gender="female", year=1995, month=7, day=22, hour=15),
]

# 每组输入取几批。抽样有随机性，1 批 6 个名字的命中率会在 0%~100% 之间跳。
REPEAT = 3


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


@pytest.fixture(scope="module")
def samples(engine) -> dict:
    """
    {style: (选该气质的名字, 不选气质的名字)}。

    每组输入取 **3 批**，不是 1 批：抽样本身带随机（组名阶段会打乱 tier 顺序），
    单批只出 6 个名字，命中率在 0%~100% 之间跳，拿它当判据必然随机失败。
    3 批 × 4 组 = 72 个名字后，实测命中率稳定在 41%~68%（见下方各条的基线）。
    """
    base: list = []
    for case in CASES:
        for _ in range(REPEAT):
            base += engine.generate_names(**case, name_length=2, max_results=6)["names"]

    out: dict[str, tuple] = {}
    for code in STYLE_CULTURE_CHARS:
        picked: list = []
        for case in CASES:
            for _ in range(REPEAT):
                picked += engine.generate_names(
                    **case, name_length=2, max_results=6, style=code
                )["names"]
        out[code] = (picked, base)
    return out


def _chars_of(name: dict) -> set:
    return {c.get("char") for c in name.get("chars_info", []) if c.get("char")}


def _name_hit_rate(names: list, family: set) -> float:
    """至少含一个该字族字的名字占比 —— 用户实际看到的口径。"""
    if not names:
        return 0.0
    return sum(1 for n in names if _chars_of(n) & family) / len(names)


# --------------------------------------------------------------------------- #
# 1. 字表本身
# --------------------------------------------------------------------------- #

def test_every_style_has_enough_family_chars():
    """每个气质至少 8 字：少于这个数，硬名额取不满，效果等于没有"""
    thin = {
        code: len(chars)
        for code, chars in STYLE_CULTURE_CHARS.items()
        if len(chars) < 8
    }
    assert not thin, f"这些气质的字族太少：{thin}"


def test_style_family_covers_all_styles():
    """8 个气质一个都不能漏 —— 漏了就等于用户选它时系统装没看见"""
    missing = set(STYLE_OPTIONS) - set(STYLE_CULTURE_CHARS)
    assert not missing, f"这些气质没有字族：{missing}"
    unknown = set(STYLE_CULTURE_CHARS) - set(STYLE_OPTIONS)
    assert not unknown, f"出现了不存在的气质 code：{unknown}"


def test_style_chars_are_in_candidate_pool(candidate_pool):
    """
    字族里的字必须真的在语料里。

    否则就是空头支票：用户选了「空灵禅意」，看到理由是「多用云月苔石」，
    可引擎根本组不出带这些字的名字。
    """
    offenders: dict[str, str] = {}
    for code, chars in STYLE_CULTURE_CHARS.items():
        outside = [c for c in chars if c not in candidate_pool]
        if outside:
            offenders[code] = "".join(outside)
    assert not offenders, f"这些字不在语料候选池里：{offenders}"


def test_style_chars_are_usable_not_blacklisted():
    """
    字族里不许有「引擎永远不会用」的字（凶字 ∪ blacklist.json）。

    「在 recommend_chars 里」还不够：语料可以推荐「虚」，但 R3 会把它拦在组名之前。
    它在字族里只会让「契合点」多一条永远不会触发的死规则 ——
    这次就是这么抓到的（zen 原本含「虚」）。

    黑名单走 scripts/poetry_utils.load_blacklist（与入库 Gate 的 R3 同一个函数），
    避免测试和门禁各用一份口径。
    """
    from poetry_utils import load_blacklist

    bad = load_blacklist()
    offenders = {
        code: "".join(c for c in chars if c in bad)
        for code, chars in STYLE_CULTURE_CHARS.items()
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, (
        f"这些字族的字永远不会出现在名字里（凶字/黑名单）：{offenders}"
    )


def test_style_notes_exist_and_say_how_not_whether():
    """
    说明只讲「这个气质的字长什么样」，不讲吉凶好坏。

    与孕期页、期许 note 是同一套合规口径：不预测、不建议、不评价。
    """
    banned = ("吉凶", "大吉", "必", "一定", "旺", "克", "凶", "推荐", "最好")
    missing = [c for c in STYLE_CULTURE_CHARS if not STYLE_CULTURE_NOTES.get(c)]
    assert not missing, f"这些气质缺字族说明：{missing}"
    offenders = {
        code: note for code, note in STYLE_CULTURE_NOTES.items()
        if any(b in note for b in banned)
    }
    assert not offenders, f"这些气质说明带了判断性用语：{offenders}"


def test_style_hits_shape():
    """契合点的结构：字 + 气质 code + 说明，一个字族里没有的字不返回"""
    hits = style_hits(["云", "山"], "zen")
    assert [h["char"] for h in hits] == ["云"]
    assert hits[0]["style"] == "zen"          # 详情页靠它翻中文，不依赖请求参数
    assert hits[0]["note"] == STYLE_CULTURE_NOTES["zen"]
    # 未选气质 / 字不在族内 → 空表
    assert style_hits(["云"], None) == []
    assert style_hits(["云"], "") == []
    assert style_hits(["山"], "zen") == []
    assert style_culture_chars("nope") == set()


# --------------------------------------------------------------------------- #
# 2. 气质真的生效
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code", sorted(STYLE_CULTURE_CHARS))
def test_style_family_actually_shows_up(samples, code):
    """
    选了气质，含该字族字的名字至少占三成，且明显高于不选。

    改前按出处判：7 个气质有效，「古风雅致」倒挂。
    改后按字族判，四组输入 × 3 批实测 41%~68%（不选 3%~18%），
    单批最低会掉到 0%（大气沉稳），所以判据必须是多批聚合的平均值。
    下限取 30% 与 test_meaning_culture 同一口径 —— 卡在实测值上会变成随机失败，
    卡在「用户能不能看出来」这个语义上才稳。
    """
    picked, base = samples[code]
    family = set(STYLE_CULTURE_CHARS[code])
    sel = _name_hit_rate(picked, family)
    raw = _name_hit_rate(base, family)
    assert sel >= 0.30, (
        f"「{STYLE_OPTIONS[code]['name']}」只有 {sel:.0%} 的名字含该字族字，"
        f"低于 30% —— 用户会再次觉得「选了什么都没变化」"
    )
    assert sel >= raw + 0.15, (
        f"「{STYLE_OPTIONS[code]['name']}」选 {sel:.0%} vs 不选 {raw:.0%}，"
        f"差距不足 15pt —— 用户分辨不出选与不选"
    )


def test_classic_style_is_no_longer_inverted(samples):
    """
    「古风雅致」是本轮改造的回归点。

    改前：选它 50%、不选 67%（倒挂 17pt）—— 因为它按诗经/楚辞/汉魏/五代词判，
    而这四部典籍本就占语料六成以上，硬名额反而把席位让给了唐诗宋词。
    改后按字族判：选 62%、不选 18%。
    """
    picked, base = samples["classic"]
    family = set(STYLE_CULTURE_CHARS["classic"])
    sel = _name_hit_rate(picked, family)
    raw = _name_hit_rate(base, family)
    assert sel > raw, (
        f"「古风雅致」又倒挂了：选 {sel:.0%} vs 不选 {raw:.0%}。"
        f"字族判定被绕过时（例如退回出处判定）就会这样"
    )


def test_no_style_means_no_style_fit(engine):
    """不选气质时不许凭空冒出气质契合点（否则「契合」二字就没有信息量了）"""
    for case in CASES:
        names = engine.generate_names(**case, name_length=2, max_results=6)["names"]
        assert all(not n.get("style_fit") for n in names)


def test_style_fit_only_lists_family_chars(engine):
    """
    契合点里的每个字都必须真在该气质的字族里。

    这条防的是「为了凑文案把不相干的字也挂上理由」——
    那样用户一查就觉得系统在硬凹，比不解释更糟。
    """
    for code in STYLE_CULTURE_CHARS:
        family = set(STYLE_CULTURE_CHARS[code])
        names = engine.generate_names(
            **CASES[0], name_length=2, max_results=6, style=code
        )["names"]
        for n in names:
            for hit in n.get("style_fit") or []:
                assert hit["char"] in family, (
                    f"「{n['full_name']}」的契合字 {hit['char']} 不在 "
                    f"{code} 的字族里"
                )
                assert hit["style"] == code


def test_different_styles_give_different_char_families(engine):
    """
    不同气质要给**不同的字**，而不是同一批名字换个标签。

    「空灵禅意」出云/月/苔/石，「大气沉稳」出山/河/岳/坤 ——
    这样用户一眼能看出区别，而不是「换了一批但还是这类名字」。
    """
    def hit_chars(code: str) -> set:
        out: set = set()
        for case in CASES:
            names = engine.generate_names(
                **case, name_length=2, max_results=6, style=code
            )["names"]
            for n in names:
                out |= {h["char"] for h in (n.get("style_fit") or [])}
        return out

    zen = hit_chars("zen")
    grand = hit_chars("grand")
    assert zen and grand
    overlap = zen & grand
    assert len(overlap) <= 2, (
        f"「空灵禅意」与「大气沉稳」的契合字重合太多：{overlap}，说明字族没分开"
    )
    assert {"云", "月", "苔", "石", "泉", "幽", "静"} & zen, (
        f"空灵类的契合字里没有任何「云月苔石」：{zen}"
    )
    assert {"山", "河", "海", "岳", "坤", "天", "宇"} & grand, (
        f"大气类的契合字里没有任何「山河岳坤」：{grand}"
    )


# --------------------------------------------------------------------------- #
# 3. 接口层
# --------------------------------------------------------------------------- #

def test_route_exposes_style_fit():
    """契合点必须能被前端拿到（schema 漏字段时会被静默剥掉，这里守住）"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/v1/generate", json={
        "surname": "林", "gender": "male",
        "year": 1990, "month": 5, "day": 20, "hour": 12,
        "name_length": 2, "max_results": 6,
        "style": "zen", "shuffle": False,
    })
    assert resp.status_code == 200, resp.text
    names = resp.json()["names"]
    assert names, "接口没有返回名字"
    assert "style_fit" in names[0], "响应里没有 style_fit 字段"
    hits = [h for n in names for h in (n.get("style_fit") or [])]
    assert hits, "一个气质契合点都没有，前端无从解释"
    assert all(h.get("char") and h.get("style") and h.get("note") for h in hits)


# --------------------------------------------------------------------------- #
# 4. 页面上真的出现了（后端给了字段，前端不渲染等于没做）
# --------------------------------------------------------------------------- #

def test_result_card_renders_both_fit_kinds():
    """
    结果卡要能同时显示「期许契合」与「气质契合」。

    卡片只放一行：期许优先、没有期许时退回气质（见 result.js 的注释）。
    这里守的是两件事：标签前缀跟着 fitLabel 走（不能写死「契合」），
    以及装饰逻辑里两条分支都在 —— 只留一条时页面不报错，只是气质永远不显示。
    """
    js = (PROJECT_ROOT / "miniprogram" / "pages" / "result" / "result.js").read_text(
        encoding="utf-8"
    )
    wxml = (PROJECT_ROOT / "miniprogram" / "pages" / "result" / "result.wxml").read_text(
        encoding="utf-8"
    )
    assert "n.style_fit" in js, "result.js 没读 style_fit，气质契合点不会显示"
    assert "fitLabel" in js and "{{item.fitLabel}}" in wxml, (
        "标签前缀没跟着 fitLabel 走，气质那一行会印成「契合「空灵禅意」」"
    )
    assert "{{item.fitLine}}" in wxml


def test_detail_page_shows_style_fit_block():
    """详情页要有一块单独说气质（与期许那块分开：一个是风格，一个是愿望）"""
    js = (PROJECT_ROOT / "miniprogram" / "pages" / "detail" / "detail.js").read_text(
        encoding="utf-8"
    )
    wxml = (PROJECT_ROOT / "miniprogram" / "pages" / "detail" / "detail.wxml").read_text(
        encoding="utf-8"
    )
    assert "name.style_fit" in js and "styleFit" in js
    assert "契合你选的气质" in wxml and "{{styleFit.chars}}" in wxml
