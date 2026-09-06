"""名字两字顺序（字序）逻辑测试。

验证「颠倒一下更好」的治本修复：
- 原文语序优先：同源组合时按诗句原文先后定序；
- 音韵兜底：字不在原文时，末字平声收尾优先；
- 同声调时保持原序（亲和分高的字在前）。
"""
from app.services.naming_engine import NamingEngine


def _c(e, ch):
    return e.char_db.get_char(ch)


def test_order_follows_original_sequence():
    """两字都在出处原文里时，按原文出现先后定序。"""
    e = NamingEngine()
    # 星汉灿烂 → 汉在前、灿在后
    f, s = e._order_two_chars({"text": "星汉灿烂，若出其里"}, _c(e, "灿"), _c(e, "汉"))
    assert f["char"] == "汉" and s["char"] == "灿"
    # 金阶玉为堂 → 金在前、玉在后
    f, s = e._order_two_chars({"text": "乃到王母台，金阶玉为堂"}, _c(e, "玉"), _c(e, "金"))
    assert f["char"] == "金" and s["char"] == "玉"


def test_order_phonetic_prefers_flat_tone_last():
    """字不在原文时，末字平声收尾优先（月明 优于 明月）。"""
    e = NamingEngine()
    ming, yue = _c(e, "明"), _c(e, "月")
    assert e._order_phonetic_better(ming, yue) is False  # 明不该放前
    assert e._order_phonetic_better(yue, ming) is True   # 月放前（月明）更好


def test_order_phonetic_same_tone_keeps_order():
    """两字同声调时无法区分，保持原序（亲和分高的在前）。"""
    e = NamingEngine()
    chuan, feng = _c(e, "川"), _c(e, "风")
    assert e._order_phonetic_better(chuan, feng) is True
