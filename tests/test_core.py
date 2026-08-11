"""
核心引擎功能测试
"""

import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.services.naming_engine import NamingEngine


def test_bazi():
    """测试八字排盘"""
    print("=" * 60)
    print("测试八字排盘")
    print("=" * 60)

    # 测试：2025年1月15日 10:00 男
    result = BaziEngine.generate_bazi(2025, 1, 15, 10, 0, "male")
    print(f"公历: {result['solar_date']}")
    print(f"农历: {result['lunar_date']}")
    print(f"生肖: {result['shengxiao']}")
    print(f"四柱: {result['four_pillars']}")
    print(f"日主: {result['day_master']} ({result['day_master_wuxing']})")
    print(f"五行分布: {result['wuxing']['percentages']}")
    print(f"缺失五行: {result['wuxing']['missing']}")
    print(f"身强身弱: {result['xiyong']['strength_label']} ({result['xiyong']['strength_ratio']}%)")
    print(f"喜用神五行: {result['xiyong']['xi_wuxing']}")
    print(f"用神: {result['xiyong']['yong_wuxing']}")
    print()


def test_char_db():
    """测试字库"""
    print("=" * 60)
    print("测试字库")
    print("=" * 60)

    db = CharDatabase()
    print(f"总字数: {db.total}")

    # 按五行查
    jin_chars = db.get_by_wuxing("金", "male")
    print(f"金字(男): {[c['char'] for c in jin_chars[:10]]}")

    # 查单字
    info = db.get_char("明")
    if info:
        print(f"「明」: 五行={info['wuxing']}, 笔画={info['kangxi_strokes']}, 拼音={info['pinyin']}")
    print()


def test_poetry_db():
    """测试诗词库"""
    print("=" * 60)
    print("测试诗词库")
    print("=" * 60)

    db = PoetryDatabase()
    print(f"总条数: {db.total}")

    # 按字查
    poems = db.get_by_char("明")
    for p in poems[:3]:
        print(f"  「{p['source']}·{p['title']}」{p['text'][:30]}...")
    print()


def test_phonetics():
    """测试音律评分"""
    print("=" * 60)
    print("测试音律评分")
    print("=" * 60)

    for name in ["张伟", "李清照", "王子轩", "陈嘉嘉"]:
        result = PhoneticsScorer.analyze(name)
        print(f"  {name}: 拼音={result['pinyins']}, 声调={result['tones']}, "
              f"平仄={result['rhythm']}, 评分={result['score']}")
    print()


def test_wuge():
    """测试五格数理"""
    print("=" * 60)
    print("测试五格数理")
    print("=" * 60)

    for surname, given in [("张", "伟"), ("李", "清照"), ("王", "子轩")]:
        result = WugeScorer.calculate(surname, given)
        print(f"  {surname}{given}: 天格={result['tian_ge']['value']}({result['tian_ge']['luck']})"
              f" 人格={result['ren_ge']['value']}({result['ren_ge']['luck']})"
              f" 地格={result['di_ge']['value']}({result['di_ge']['luck']})"
              f" 总格={result['zong_ge']['value']}({result['zong_ge']['luck']})"
              f" 总分={result['total_score']}")
    print()


def test_naming_engine():
    """测试起名引擎"""
    print("=" * 60)
    print("测试起名引擎（完整流程）")
    print("=" * 60)

    engine = NamingEngine()

    # 测试：姓张，男，2025年1月15日 10:00
    result = engine.generate_names(
        surname="张",
        gender="male",
        year=2025,
        month=1,
        day=15,
        hour=10,
        minute=0,
        name_length=2,
        max_results=5,
    )

    print(f"\n八字: {result['bazi']['four_pillars']}")
    print(f"日主: {result['bazi']['day_master']} ({result['bazi']['day_master_wuxing']})")
    print(f"喜用神: {result['bazi']['xiyong']['xi_wuxing']}")
    print(f"\n候选名字（共{result['total']}个，显示前5）:\n")

    for i, name in enumerate(result["names"], 1):
        print(f"  {i}. {name['full_name']}  综合评分: {name['scores']['overall']}")
        print(f"     拼音: {name['phonetics']['pinyins']}  音律: {name['phonetics']['score']}  五格: {name['scores']['wuge']}  八字: {name['scores']['bazi']}")
        if name["poetry"]:
            print(f"     出处: 「{name['poetry']['source']}·{name['poetry']['title']}」{name['poetry']['text']}")
        print(f"     寓意: {name['meaning']}")
        print()

    # 测试不带八字
    print("-" * 40)
    print("测试不带八字分析（只按字库+诗词）:")
    result2 = engine.generate_names(
        surname="李",
        gender="female",
        name_length=2,
        max_results=3,
        use_bazi=False,
    )
    for i, name in enumerate(result2["names"], 1):
        print(f"  {i}. {name['full_name']}  综合评分: {name['scores']['overall']}")
        if name["poetry"]:
            print(f"     出处: 「{name['poetry']['source']}·{name['poetry']['title']}」{name['poetry']['text']}")
    print()


if __name__ == "__main__":
    test_bazi()
    test_char_db()
    test_poetry_db()
    test_phonetics()
    test_wuge()
    test_naming_engine()
    print("=" * 60)
    print("全部测试完成！")
    print("=" * 60)
