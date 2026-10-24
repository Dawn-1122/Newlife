"""姓名拆分（姓 / 名分离）。

为什么单独一个模块：起名、释名、批量对比三个入口都要拆姓名，
此前 `api/routes.py` 里内联了一份只有 9 个复姓的短表，而
`core/constants.COMPOUND_SURNAMES` 有 18 个 —— 于是「东方明月」被拆成
姓「东」名「方明月」，「夏侯清和」被拆成姓「夏」名「侯清和」，
五格（天格＝姓笔画＋1）与音律整体算错，而后端从不报错。

把拆分规则收到一处，只留一份表、一条规则，三个入口共用。
"""

from __future__ import annotations

from app.core.constants import COMPOUND_SURNAMES

# 按字数降序：将来若加入三字姓，也不会被两字姓抢先命中
_SURNAMES_BY_LEN = tuple(sorted(COMPOUND_SURNAMES, key=len, reverse=True))

# 姓名总长上限（与 schemas 的 max_length=10 一致）
MAX_FULL_NAME_LEN = 10


def split_full_name(full_name: str) -> tuple[str, str]:
    """把完整姓名拆成 (姓, 名)。复姓优先匹配。

    >>> split_full_name("欧阳清和")
    ('欧阳', '清和')
    >>> split_full_name("林清野")
    ('林', '清野')

    仅当姓之后还留有名字时才按复姓拆：单独输入「欧阳」两字时，
    按单姓处理（姓欧名阳），否则名会是空串。
    """
    name = (full_name or "").strip()
    if not name:
        return "", ""

    for surname in _SURNAMES_BY_LEN:
        if name.startswith(surname) and len(name) > len(surname):
            return surname, name[len(surname):]

    return name[0], name[1:]


def is_han(ch: str) -> bool:
    """是否汉字（含扩展区）。

    字库里有生僻字（level 一/二/扩展），故不能只判基本区 U+4E00–9FFF，
    否则「䶮」这类扩展字会被当成非法输入挡掉。
    """
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF        # 基本区
        or 0x3400 <= code <= 0x4DBF     # 扩展 A
        or 0xF900 <= code <= 0xFAFF     # 兼容汉字
        or 0x20000 <= code <= 0x2FA1F   # 扩展 B 及以后
    )


# 少数民族姓名与译名里的间隔号，不算非法字符
_LEGAL_SEPARATORS = "·•・"


def is_valid_full_name(full_name: str) -> tuple[bool, str]:
    """姓名合法性（释名 / 批量对比入口共用）。返回 (是否合法, 不合法原因)。"""
    name = (full_name or "").strip()
    if len(name) < 2:
        return False, "姓名至少 2 个字"
    if len(name) > MAX_FULL_NAME_LEN:
        return False, "姓名最多 %d 个字" % MAX_FULL_NAME_LEN
    for ch in name:
        # 混进字母/数字/空格时，逐字解析会拿到空拼音与「未知」五行，
        # 结果看着像真的、其实是噪声 —— 不如直接说清楚
        if not is_han(ch) and ch not in _LEGAL_SEPARATORS:
            return False, "姓名只能用汉字"
    return True, ""
