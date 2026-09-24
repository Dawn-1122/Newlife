"""字对复核策略的一致性约束。

存在的原因（2026-09-24）：`pair_review.SYSTEM_PROMPT` 的「反例四类」里曾把
**「锦瑟」**当反例列举，而 `PROTECTED` 又把「锦瑟」列为「复核不得剔除」
——同一条词同时是反例和保护对象。这不会报错、不会崩，只会让复核**悄悄误杀**
传诵千年的名用词（锦瑟就是这么被误杀过一次才补进 PROTECTED 的）。

同一个提示词的另一面是**漏放**：`「呦鸣」`（「呦呦鹿鸣」的跨字拼接）被放行并产出。
所以这里把两类约束都固定下来：

1. PROTECTED 与 BLOCKLIST 不得有交集；
2. PROTECTED 里的词不得出现在提示词的「反例」段落里（结构性防止矛盾复现）；
3. 「意象＋动作/声音/色彩」的经典组合必须在 PROTECTED 里（用户明确要求保留）；
4. 跨字机械拼接必须在 BLOCKLIST 里；
5. 落盘的 name_pairs.json 不得残留 BLOCKLIST 里的组合。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAIR_REVIEW = PROJECT_ROOT / "scripts" / "pair_review.py"
NAME_PAIRS = PROJECT_ROOT / "data" / "poetry" / "name_pairs.json"

# 提示词中「反例四类」段落的起止锚点
NEG_START = "只有在属于下面四类时才标"
NEG_END = "宁漏勿滥"

# 用户明确要求保留的「意象＋动作/声音/色彩」经典组合（2026-09-24）
CLASSIC_IMAGERY = [
    "鹿鸣", "鹤鸣", "白鹿", "青崖", "蝉鸣", "疏影", "暗香", "素月",
]

# 跨字机械拼接：应取「鹿鸣」，不得取「呦鹿」「呦鸣」
MECHANICAL_SPLICES = ["呦鹿", "呦鸣"]


def _load_constants() -> dict:
    """用 AST 从 pair_review.py 取常量，避免 import 其运行时依赖（LLM/async）。"""
    tree = ast.parse(PAIR_REVIEW.read_text(encoding="utf-8"))
    wanted = {"PROTECTED", "BLOCKLIST", "SYSTEM_PROMPT"}
    out: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in wanted:
                    out[tgt.id] = ast.literal_eval(node.value)
    missing = wanted - set(out)
    assert not missing, f"未能从 pair_review.py 解析出常量: {sorted(missing)}"
    return out


@pytest.fixture(scope="module")
def consts() -> dict:
    return _load_constants()


def test_protected_and_blocklist_are_disjoint(consts):
    """保护名单与硬黑名单不得有交集 —— 否则「保护」与「剔除」两套逻辑互相打架。"""
    overlap = consts["PROTECTED"] & consts["BLOCKLIST"]
    assert not overlap, f"以下词同时出现在 PROTECTED 与 BLOCKLIST：{sorted(overlap)}"


def test_protected_words_absent_from_negative_examples(consts):
    """PROTECTED 的词不得出现在提示词的「反例四类」里。

    「锦瑟」当初就是这样被误杀的：它既在反例例举里、又在保护名单里。
    """
    prompt = consts["SYSTEM_PROMPT"]
    i, j = prompt.find(NEG_START), prompt.find(NEG_END)
    assert i != -1 and j != -1 and i < j, "提示词结构变了，请同步更新本测试的锚点"
    negative_section = prompt[i:j]
    clashes = sorted(w for w in consts["PROTECTED"] if w in negative_section)
    assert not clashes, (
        f"这些词被列为反例，但同时在 PROTECTED 保护名单里：{clashes}"
    )


def test_classic_imagery_words_are_protected(consts):
    """意象＋动作/声音/色彩的经典组合必须受保护（用户 2026-09-24 明确要求）。

    典型是「鹿鸣」——《诗经·小雅·鹿鸣》「呦呦鹿鸣，食野之苹」。
    这类词是诗词起名的上等素材，不得被复核当作「动物名」剔除。
    """
    missing = [w for w in CLASSIC_IMAGERY if w not in consts["PROTECTED"]]
    assert not missing, f"以下经典意象组合未进入 PROTECTED：{missing}"


def test_mechanical_splices_are_blocked(consts):
    """跨字拼接必须被硬黑名单挡住。

    「呦呦鹿鸣」应取「鹿鸣」；取「呦鹿」「呦鸣」属于把叠词的一字与后文硬凑。
    「呦鹿」2026-09-22 已封，「呦鸣」是同类漏网，2026-09-24 补封。
    """
    missing = [w for w in MECHANICAL_SPLICES if w not in consts["BLOCKLIST"]]
    assert not missing, f"以下跨字拼接未进入 BLOCKLIST：{missing}"


def test_classic_imagery_not_blocked(consts):
    """反向保险：经典意象组合绝不能被写进硬黑名单。"""
    blocked = [w for w in CLASSIC_IMAGERY if w in consts["BLOCKLIST"]]
    assert not blocked, f"以下经典意象组合被误列入 BLOCKLIST：{blocked}"


@pytest.mark.skipif(not NAME_PAIRS.exists(), reason="name_pairs.json 不存在")
def test_name_pairs_free_of_blocklisted_combos(consts):
    """落盘字对不得残留硬黑名单组合。

    失败说明新增了 BLOCKLIST 项但没跑 `pair_review.py --blocklist-only` 应用。
    """
    data = json.loads(NAME_PAIRS.read_text(encoding="utf-8"))
    bad = sorted({
        "".join(pair) if isinstance(pair, list) else str(pair)
        for pairs in data.values()
        for pair in pairs
    } & consts["BLOCKLIST"])
    assert not bad, (
        f"name_pairs.json 残留黑名单组合 {bad}；"
        f"请运行：venv/bin/python scripts/pair_review.py --blocklist-only"
    )


@pytest.mark.skipif(not NAME_PAIRS.exists(), reason="name_pairs.json 不存在")
def test_classic_imagery_still_present_in_name_pairs(consts):
    """「鹿鸣」这类词若原本已在字对库里，就不得因复核而消失。"""
    data = json.loads(NAME_PAIRS.read_text(encoding="utf-8"))
    present = {
        "".join(pair) if isinstance(pair, list) else str(pair)
        for pairs in data.values()
        for pair in pairs
    }
    # 只在「库里本来就有」时校验，避免对尚未收录的词产生假失败
    expected = [w for w in ("鹿鸣", "鹤鸣") if w in present]
    assert expected, "「鹿鸣」「鹤鸣」都不在字对库里了，疑似被整批误杀"
