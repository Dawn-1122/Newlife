"""
T3 · 诗词标注提示词

为 LLM 批量标注诗词提供系统提示词与用户提示词构建。
硬约束（违反即判无效）：
1. recommend_chars 每个字必须从「可用字候选集」中选取（候选集已预筛：字库 luck=吉 且 出现在诗句中 且 非黑名单 且 非功能字）
2. 2~5 个字，字形端正、声韵协调，只取有明确文化寓意、适合人名的实词
3. emotion 仅 喜庆/中性/哀伤；哀伤 → recommend_chars 置空 []
4. gender 仅 男/女/中
5. 只输出合法 JSON（配合 response_format=json_object）
"""

from __future__ import annotations

# 功能字/数字/虚词/代词/助词黑名单（无实际起名寓意的字，推荐字一律避开）
# 作为字符串供提示词展示，也作为 set 供 annotator 预筛候选集与后置过滤复用
FUNCTION_WORDS_STR = (
    "一、二、三、四、五、六、七、八、九、十、百、千、万、亿、零、两、几、双、"
    "须、若、其、此、之、吾、予、余、尔、汝、彼、孰、何、奚、"
    "而、且、乃、亦、乎、者、也、焉、哉、矣、耳、兮、些、夫、盖、"
    "于、以、与、及、为、因、由、从、至、到、有、无、不、非、未、"
    "勿、毋、莫、唯、惟、曰、云、言、只、则、即、虽、然、会、行、"
    "奉、将、自、相、见、是、所、可、得"
)
FUNCTION_WORDS = set(FUNCTION_WORDS_STR.replace("、", ""))


SYSTEM_PROMPT = (
    "你是一位精通中国传统文化、诗词典故与姓名学的专家。"
    "你的任务是为给定的诗词摘句做「起名标注」：判断其情感基调，并从中精选适合作为人名的汉字。"
    "你只输出一个合法 JSON 对象，不输出任何解释、前后缀或 markdown 代码块。"
)

OUTPUT_TEMPLATE = """{
  "recommend_chars": ["维", "新"],
  "emotion": "喜庆",
  "gender": "男",
  "imagery": ["革新", "承前启后"],
  "scene": "寄托变革创新之志"
}"""

HARD_RULES = """硬性规则（必须全部满足）：
1. recommend_chars 中的每个字【必须】从上面「可用字候选集」里选取，不得自造、不得超出候选集；共 2~5 个字。
2. 推荐字要寓意积极、字形端正、声韵协调、不过于冷僻；优先选诗句中实际出现且含义吉美的字。
3. 【避开功能字】不得推荐数字、虚词、代词、助词等无实际文化寓意的功能字（如：一、二、三、四、五、六、七、八、九、十、百、千、万、须、若、其、此、之、吾、而、且、乃、亦、乎、者、也、焉、哉、会、行、奉、将、自、所、可、得 等）。recommend_chars 只取有明确文化寓意、适合人名的实词（如：维、新、明、德、嘉、兰、芳、玉、清、安、泰、和、瑞、贤、俊、志、远、修、博、文 等）。
4. emotion 只能是「喜庆」「中性」「哀伤」三者之一。整句基调悲苦、伤悼、离愁、衰亡 → 判「哀伤」，且 recommend_chars 必须为空数组 []。
5. 基调欢快、祝福、昂扬、祥和 → 判「喜庆」；其余 → 判「中性」。
6. gender 只能是「男」「女」「中」，根据意象判断更适合男孩、女孩或中性。
7. imagery 给 2~4 个意象词；scene 用一句话概括该句适合寄托的寓意。
8. 只输出一个 JSON，字段齐全，不要输出任何解释。"""


def build_user_prompt(entry: dict, candidate_chars: list[dict]) -> str:
    """构建用户提示词。

    Args:
        entry: {source, title, author, dynasty, text, citation}
        candidate_chars: 可用字候选集（已预筛），每个为 {char, pinyin, wuxing, meaning}
    """
    if candidate_chars:
        char_lines = []
        for c in candidate_chars:
            meaning = (c.get("meaning") or "").split("，")[0]
            char_lines.append(f"- 「{c['char']}」五行{c.get('wuxing', '?')}，{meaning}")
        char_block = "\n".join(char_lines)
    else:
        char_block = "（无可用候选字）"

    return f"""【诗句】
{entry['text']}

【出处】
{entry.get('citation', '')} ｜ {entry.get('author', '佚名')}（{entry.get('dynasty', '')}）｜ {entry.get('source', '')}

【可用字候选集】（推荐字只能从这里选）
{char_block}

【输出 JSON 模板】
{OUTPUT_TEMPLATE}

【{HARD_RULES}】"""
