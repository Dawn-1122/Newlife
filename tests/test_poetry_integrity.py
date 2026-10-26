"""诗词库的字段自洽性。

挡住的是「静默」类错误：数据不合法但不报错，只是某个字永远出不来。

已经出过一次：`poem_x045`《洛神赋》摘句「翩若惊鸿，婉若游龙」，
推荐字只标了「婉、若、鸿」，漏了「龙」。于是「若龙」这个名字
在男女两个口径下都不可达——原句里明明有「游龙」。
这种遗漏不会触发 R1~R11 任何一条：龙在字库、是吉字、不在黑名单，
只是没人把它写进那一行。

同一条也守住反向错误：推荐字必须是原句里的字。若允许脱离原文，
「会当凌绝顶」可以推荐「峰」，用户看到的名字与给出的理由是两回事。
"""

import json
from pathlib import Path

import pytest

POETRY_DIR = Path(__file__).resolve().parents[1] / "data" / "poetry"

# 已知例外：原句无此字，但该字是这句最自然的取名落点（写出理由，不是静默放过）。
KNOWN_OFFTEXT = {
    "poem_0022": {"峰"},  # 会当凌绝顶，一览众山小 —— 峰是「凌绝顶」的对象，句外补出
}


def load_poems() -> list[dict]:
    poems: list[dict] = []
    for path in sorted(POETRY_DIR.glob("poetry*.json")):
        if path.name == "poetry.schema.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        poems += (data.get("poems") if isinstance(data, dict) else data) or []
    return poems


@pytest.fixture(scope="module")
def poems() -> list[dict]:
    return load_poems()


def test_recommend_chars_come_from_the_line(poems):
    """推荐字必须在原句里出现（例外见 KNOWN_OFFTEXT）。"""
    bad = []
    for p in poems:
        text = p.get("text") or ""
        allowed = KNOWN_OFFTEXT.get(p.get("id"), set())
        missing = [c for c in (p.get("recommend_chars") or [])
                   if c not in text and c not in allowed]
        if missing:
            bad.append(f"{p.get('id')}「{text}」缺 {''.join(missing)}")
    assert not bad, "推荐字不在原句内：\n" + "\n".join(bad)


def test_luoshen_fu_line_offers_the_whole_dragon(poems):
    """回归点：洛神赋「婉若游龙」那句，推荐字要含「龙」。

    这条不是为某个名字开的特例，而是「原句里成句的两个实词都要能取」。
    漏标「龙」的代价是「若龙」零可达，而它在字库、吉、中性，本该可用。
    """
    entry = next(p for p in poems if p.get("id") == "poem_x045")
    assert "游龙" in entry["text"]
    assert "龙" in entry["recommend_chars"]
