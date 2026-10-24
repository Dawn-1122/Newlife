"""姓名静态解析（释名 / 批量对比共用）。

从 `api/routes.py` 的 `analyze_name` 提炼而来：同一段
「拆姓 → 逐字取信息 → 音律 → 五格 → 八字匹配 → 诗词出处」
既被单个释名用，也被「测候选名 / 双名对比」的批量接口用。

放这里才有意义：两条入口若各写一遍，同一个名字在释名页和对比页会拿到
不同的分数与描述 —— 那是最难向用户解释的一类不一致（「刚才还是 82 分」）。

纯函数，不依赖 FastAPI，单测可直接调用。
"""

from __future__ import annotations

from app.core.names import split_full_name
from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase
from app.services.name_verdict import build_verdict
from app.services.phonetics import PhoneticsScorer
from app.services.poetry_database import PoetryDatabase
from app.services.wuge import WugeScorer

# 五格计算异常时的兜底（保持既有返回结构，前端不用判空）
_WUGE_FALLBACK = {"total_score": 0, "description": "数理计算异常"}


def _char_entry(char: str, char_db: CharDatabase) -> dict:
    """单个字的展示信息；字库未收时给出可读的占位而不是空白。"""
    info = char_db.get_char(char)
    if not info:
        return {
            "char": char,
            "pinyin": "",
            "wuxing": "未知",
            "kangxi_strokes": 0,
            "meaning": "字库中暂无此字信息",
        }
    return {
        "char": info["char"],
        "pinyin": info["pinyin"],
        "wuxing": info["wuxing"],
        "kangxi_strokes": info["kangxi_strokes"],
        "meaning": info["meaning"],
        "shuowen": info.get("shuowen", ""),
        "detail": info.get("detail", ""),
    }


def analyze_full_name(
    full_name: str,
    *,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    hour: int | None = None,
    minute: int | None = None,
    gender: str | None = None,
) -> dict:
    """解析一个完整姓名。结构与 `/analyze` 的历史返回完全一致，只多一个 `verdict`。

    `hour` 缺省为 12（午时）：释名页没问时辰时，用午时排一个可用的盘，
    但 `verdict` 与页面都不会把时柱当成用户给的事实来展示（见 P1-4）。
    """
    full_name = (full_name or "").strip()
    surname, given_name = split_full_name(full_name)

    char_db = CharDatabase()
    phonetics = PhoneticsScorer()
    wuge_scorer = WugeScorer()

    chars_info = [_char_entry(c, char_db) for c in given_name]

    phonetics_result = phonetics.analyze(full_name)

    try:
        wuge_result = wuge_scorer.calculate(surname, given_name)
    except Exception:
        wuge_result = dict(_WUGE_FALLBACK)

    bazi_match = None
    if year and month and day:
        bazi = BaziEngine.generate_bazi(
            year, month, day,
            hour if hour is not None else 12,
            minute if minute is not None else 0,
            gender or "male",
        )
        xiyong = bazi["xiyong"]["xi_wuxing"]
        matched = sum(1 for ci in chars_info if ci.get("wuxing") in xiyong)
        bazi_match = {
            "bazi": bazi,
            "match_score": 60 + int(matched / max(len(chars_info), 1) * 40),
            "matched_wuxing": [ci["wuxing"] for ci in chars_info if ci.get("wuxing") in xiyong],
        }

    poetry_db = PoetryDatabase()
    poetry_matches: list[dict] = []
    for ci in chars_info:
        for p in poetry_db.get_by_char(ci["char"]):
            if p not in poetry_matches:
                poetry_matches.append(p)

    result = {
        "full_name": full_name,
        "surname": surname,
        "given_name": given_name,
        "chars_info": chars_info,
        "phonetics": phonetics_result,
        "wuge": wuge_result,
        "bazi_match": bazi_match,
        # 时辰是不是用户真的给的：false 时页面不展示时柱，
        # 只说明「时辰未知，时柱不参与推断」（不能把内部默认的午时当事实）
        "hour_known": hour is not None,
        "poetry": poetry_matches[0] if poetry_matches else None,
        "poetry_list": poetry_matches[:3],
    }
    # 收束语（释名页的「整体印象」）。放在后端算，前端只负责显示：
    # 换端（小程序 / 网页 / 分享页）时口径才一致。
    result["verdict"] = build_verdict(result)
    return result
