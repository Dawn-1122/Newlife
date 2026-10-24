"""单字名的名字感分级（第三道闸的单字分支）。

背景：`pair_taste.json` 的两字分级只管字对，单字名（name_length=1）此前在 `emit()`
里被统一写成 3 分，等于**整条单字路径不过闸**——实测 8 组输入可枚举出 350 个单字名，
「瑰/甘/垂/蓬/夜/洲」这类一路出到结果页。

单字的判据与字对不同：一个字要**独自立得住**，不能靠搭档衬托（「清」单独是名字，
「瑰」不是）。因此单独一张 `single` 表，不共用字对分数。

这一组测试守四条契约：
1. 单字表与生成脚本同源（改了脚本忘了重建数据会红灯）；
2. 屏蔽档一个都不许漏出——**包括不许用「全屏蔽时退回全量」这种兜底**；
3. 未定级的字默认 1 分（白名单外不出），与字对策略一致；
4. 文件缺 `single` 段时降级为旧行为（3 分），不让引擎哑掉。
"""

import json
import sys
from pathlib import Path

import pytest

from app.services.naming_engine import NamingEngine

ROOT = Path(__file__).resolve().parents[1]
TASTE = ROOT / "data" / "poetry" / "pair_taste.json"

# 单字名的样本面：四个姓 × 两性，覆盖出声最多的几类姓氏意象
SURNAMES = ("林", "顾", "江", "沈")
GENDERS = ("male", "female")


@pytest.fixture(scope="module")
def engine():
    return NamingEngine()


def _gen_single(engine, surname, gender, **kw):
    params = dict(
        surname=surname, gender=gender, name_length=1,
        max_results=6, use_bazi=False,
    )
    params.update(kw)
    return engine.generate_names(**params)


def test_single_section_matches_script():
    """`pair_taste.json` 的 `single` 段必须与 scripts/pair_taste.py 同源。

    两边分叉的后果是「改了判据却没生效」——数据看着有、引擎读的是旧值。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import pair_taste  # noqa: E402

    data = json.loads(TASTE.read_text(encoding="utf-8"))
    assert "single" in data, "pair_taste.json 缺 single 段，请跑 pair_taste.py --build"

    single = data["single"]
    assert single == pair_taste.single_scores(), (
        "single 段与 scripts/pair_taste.py 不一致，请跑 --build 重建"
    )
    assert set(single.values()) <= {1, 3, 4, 5}, "单字分级只允许 1/3/4/5"
    assert sum(1 for v in single.values() if v == 5) >= 10, "单字 5 分档不应为空"


def test_banned_single_chars_never_appear(engine):
    """屏蔽档单字一个都不许出现在产出里。

    这是本文件的**核心回归**：第一版闸门写了「全被屏蔽时退回全量」的兜底，
    实测量出 3/36 个屏蔽字（瑰/甘/垂）。兜底看起来是防空白，实际是把闸门拆了。
    """
    single = json.loads(TASTE.read_text(encoding="utf-8"))["single"]
    leaked = set()
    produced = 0
    for surname in SURNAMES:
        for gender in GENDERS:
            for _ in range(3):
                r = _gen_single(engine, surname, gender)
                for n in r["names"]:
                    g = n["given_name"]
                    assert len(g) == 1, f"单字模式出了多字名：{g}"
                    produced += 1
                    if single.get(g, 1) <= 1:
                        leaked.add(g)
    assert produced, "单字名一个都没出来，生成链路可能坏了"
    assert not leaked, f"单字屏蔽档漏出：{sorted(leaked)}"


def test_gate_does_not_starve_the_pool(engine):
    """闸门不能把关得太死——每类样本都还得有名字可选。

    屏蔽档占到四成左右，若某姓氏的推荐字恰好集中在屏蔽档，就会一片空白。
    这条盯的是「过滤做过头」，与上一条互补。
    """
    for surname in SURNAMES:
        for gender in GENDERS:
            r = _gen_single(engine, surname, gender)
            assert r["names"], f"{surname}/{gender} 单字名全空，闸门可能过严"


def test_output_taste_matches_char_table(engine):
    """产出的 `_taste` 必须来自单字表，而不是 `emit()` 里写死的 3。"""
    single = json.loads(TASTE.read_text(encoding="utf-8"))["single"]
    r = _gen_single(engine, "林", "female")
    assert r["names"], "前置条件：应有结果"
    for n in r["names"]:
        ch = n["given_name"]
        assert n["_taste"] == single.get(ch, 1), f"{ch} 的档位没走单字表"


def test_ungraded_char_is_blocked(engine):
    """白名单外默认 1 分（不出）——与字对「未定级即屏蔽」的策略对齐。"""
    assert engine._char_taste("龘") == 1
    assert engine._char_taste("清") == 5


def test_missing_single_section_degrades(monkeypatch, tmp_path):
    """`single` 段缺失时降级为 3 分，旧行为仍能出名字。"""
    data = json.loads(TASTE.read_text(encoding="utf-8"))
    data.pop("single", None)
    stripped = tmp_path / "pair_taste.json"
    stripped.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(NamingEngine, "_TASTE_FILE", stripped)
    e = NamingEngine()
    assert e.char_taste == {}, "缺 single 段时 char_taste 应为空（触发降级）"
    assert e._char_taste("瑰") == 3, "降级后一律 3 分"

    r = e.generate_names(
        surname="林", gender="female", name_length=1,
        max_results=6, use_bazi=False,
    )
    assert r["total"] > 0, "降级后仍应出名字"
