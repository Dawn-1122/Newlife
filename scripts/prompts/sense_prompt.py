"""
语境义项标注提示词

任务：给定「一个字 + 它所在的一句诗/一段古文」，输出**该字在这一具体语境中**
承载的意象/寓意义项（2~4 个）。

与「字典义」的区别（核心）：
- 字典义：脱语境的本义/引申义（如「清」= 清澈、清正）。
- 语境义：该字【在这句里】实际传达的意象（如「清」在「楚天千里清秋」→ 清朗、高远、澄澈；
  在「金尊清酒斗十千」→ 富贵、珍美；在「清扬婉兮」→ 清扬、婉约）。

硬性约束（违反即判无效）：
1. senses 必须紧扣【给定诗句的语境】，不得输出与该句无关的字典本义。
2. 2~4 个义项，每个 1~3 字，是意象/寓意词组（如「清朗高远」「淡泊宁静」），不是单字。
3. note 用一句话说明「该字在此句中如何取义」。
4. 只输出合法 JSON（配合 response_format=json_object）。
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是一位精通中国古典诗词与文字训诂的专家。"
    "你的任务是判断【一个字】在【其所在的那一句诗/古文】中承载的语境义项。"
    "同一个字在不同诗句里含义不同，你必须只依据给定的这一句来判断，"
    "不得输出与该句语境无关的字典本义。"
    "你只输出一个合法 JSON 对象，不输出任何解释、前后缀或 markdown 代码块。"
)

OUTPUT_TEMPLATE = """{
  "senses": ["清朗", "高远", "澄澈"],
  "note": "在「楚天千里清秋」中，「清」取秋空澄澈、境界高远之意"
}"""

HARD_RULES = """硬性规则（必须全部满足）：
1. senses 必须是【该字在这一句里】的语境义项，紧扣诗句的意象与情感；禁止输出与该句无关的字典本义。
2. senses 共 2~4 个，每个为 1~3 个字的意象/寓意词组（如「清朗」「高远」「淡泊宁静」），不得是单个字，不得重复。
3. 若该字在此句中只是虚词、语助词、无实义，或属于地名/人名的一部分，则 senses 必须返回空数组 []；【严禁】输出「助判断」「虚词」「语助」「无实义」这类元描述，也严禁把「乃/是/其/之」等虚词本身当作义项。
4. note 用一句话说明该字在此句中的取义依据（结合诗句内容，不要空泛）。
5. 只输出一个 JSON，字段齐全，不要输出任何解释。"""


def build_user_prompt(entry: dict, char: str) -> str:
    """构建用户提示词。

    Args:
        entry: 出处条目 {text, imagery, scene, citation, title, source}
        char: 待标注其语境义项的字
    """
    imagery = entry.get("imagery") or []
    imagery_block = "、".join(str(i) for i in imagery) if imagery else "（无）"
    scene = entry.get("scene") or "（无）"
    citation = entry.get("citation") or entry.get("title") or entry.get("source") or ""

    return f"""【诗句/原文】
{entry.get('text', '')}

【出处】
{citation} ｜ {entry.get('author', '佚名')}（{entry.get('dynasty', '')}）

【该句的整体意象标签（供参考，勿直接照抄）】
{imagery_block}
【该句寓意概述（供参考）】
{scene}

【待判断的字】
「{char}」

【输出 JSON 模板】
{OUTPUT_TEMPLATE}

【{HARD_RULES}】"""
