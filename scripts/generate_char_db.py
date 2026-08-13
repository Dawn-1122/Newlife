"""
汉字字库数据

包含起名常用汉字的：
- 汉字
- 拼音（含声调）
- 声调（1-4，轻声为0）
- 部首
- 康熙笔画数
- 简体笔画数
- 五行属性（金木水火土）
- 吉凶（吉/凶/中）
- 适合性别（男/女/中）
- 简要释义

数据来源：康熙字典 + 公开起名字库整理
注意：康熙笔画与简体笔画不同，五格数理计算必须用康熙笔画

增强字段（由 enrich_char_db.py 添加）：
- shuowen: 说文解字原文
- detail: 详细释义（字源、本义、引申义、起名寓意）

生成后请执行: python scripts/enrich_char_db.py
"""

import json
from pathlib import Path

# 起名常用字库（精选200字，覆盖五行各属性）
CHARS = [
    # ── 金 ──
    {"char": "金", "pinyin": "jin", "tone": 1, "radical": "金", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "黄金、金属，象征尊贵、坚毅"},
    {"char": "鑫", "pinyin": "xin", "tone": 1, "radical": "金", "kangxi_strokes": 24, "simplified_strokes": 24, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "财富兴盛，多金多福"},
    {"char": "锐", "pinyin": "rui", "tone": 4, "radical": "金", "kangxi_strokes": 15, "simplified_strokes": 12, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "锋利、敏锐，勇往直前"},
    {"char": "锋", "pinyin": "feng", "tone": 1, "radical": "金", "kangxi_strokes": 15, "simplified_strokes": 12, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "刀锋、先锋，锐不可当"},
    {"char": "铭", "pinyin": "ming", "tone": 2, "radical": "金", "kangxi_strokes": 14, "simplified_strokes": 11, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "铭刻、铭记，铭心不忘"},
    {"char": "钰", "pinyin": "yu", "tone": 4, "radical": "金", "kangxi_strokes": 13, "simplified_strokes": 10, "wuxing": "金", "luck": "吉", "gender": "女", "meaning": "珍宝、坚硬的金"},
    {"char": "锦", "pinyin": "jin", "tone": 3, "radical": "金", "kangxi_strokes": 16, "simplified_strokes": 13, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "锦绣、美好，前程似锦"},
    {"char": "银", "pinyin": "yin", "tone": 2, "radical": "金", "kangxi_strokes": 14, "simplified_strokes": 11, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "白银、财富"},
    {"char": "钧", "pinyin": "jun", "tone": 1, "radical": "金", "kangxi_strokes": 12, "simplified_strokes": 9, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "古代重量单位，引申为重要、尊贵"},
    {"char": "鉴", "pinyin": "jian", "tone": 4, "radical": "金", "kangxi_strokes": 22, "simplified_strokes": 13, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "镜子、明察、借鉴"},
    {"char": "钟", "pinyin": "zhong", "tone": 1, "radical": "金", "kangxi_strokes": 17, "simplified_strokes": 9, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "钟爱、凝聚、钟鸣"},
    {"char": "钦", "pinyin": "qin", "tone": 1, "radical": "金", "kangxi_strokes": 12, "simplified_strokes": 9, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "敬重、钦佩"},
    {"char": "镇", "pinyin": "zhen", "tone": 4, "radical": "金", "kangxi_strokes": 18, "simplified_strokes": 15, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "安定、镇守"},
    {"char": "铄", "pinyin": "shuo", "tone": 4, "radical": "金", "kangxi_strokes": 23, "simplified_strokes": 10, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "光辉明亮、熔化金属"},
    {"char": "铉", "pinyin": "xuan", "tone": 4, "radical": "金", "kangxi_strokes": 13, "simplified_strokes": 10, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "举鼎的器具，引申为栋梁之才"},
    {"char": "铠", "pinyin": "kai", "tone": 3, "radical": "金", "kangxi_strokes": 18, "simplified_strokes": 11, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "铠甲、坚强防护"},
    {"char": "铮", "pinyin": "zheng", "tone": 1, "radical": "金", "kangxi_strokes": 16, "simplified_strokes": 11, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "铁骨铮铮、刚正不阿"},
    {"char": "锡", "pinyin": "xi", "tone": 1, "radical": "金", "kangxi_strokes": 16, "simplified_strokes": 13, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "赐予、锡金"},
    {"char": "辞", "pinyin": "ci", "tone": 2, "radical": "辛", "kangxi_strokes": 19, "simplified_strokes": 13, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "文辞、辞章、修辞"},
    {"char": "诗", "pinyin": "shi", "tone": 1, "radical": "言", "kangxi_strokes": 13, "simplified_strokes": 8, "wuxing": "金", "luck": "吉", "gender": "女", "meaning": "诗歌、诗情画意"},
    {"char": "悦", "pinyin": "yue", "tone": 4, "radical": "心", "kangxi_strokes": 11, "simplified_strokes": 10, "wuxing": "金", "luck": "吉", "gender": "女", "meaning": "喜悦、欢悦"},
    {"char": "思", "pinyin": "si", "tone": 1, "radical": "心", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "思考、思念、才思敏捷"},
    {"char": "成", "pinyin": "cheng", "tone": 2, "radical": "戈", "kangxi_strokes": 7, "simplified_strokes": 6, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "成功、成就、成人之美"},
    {"char": "诚", "pinyin": "cheng", "tone": 2, "radical": "言", "kangxi_strokes": 14, "simplified_strokes": 8, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "真诚、诚实、赤诚"},
    {"char": "信", "pinyin": "xin", "tone": 4, "radical": "人", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "诚信、信仰、言而有信"},
    {"char": "瑞", "pinyin": "rui", "tone": 4, "radical": "玉", "kangxi_strokes": 14, "simplified_strokes": 13, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "祥瑞、瑞气、吉兆"},
    {"char": "睿", "pinyin": "rui", "tone": 4, "radical": "目", "kangxi_strokes": 14, "simplified_strokes": 14, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "睿智、明智、通达"},
    {"char": "尚", "pinyin": "shang", "tone": 4, "radical": "小", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "金", "luck": "吉", "gender": "男", "meaning": "崇尚、高尚、尊尚"},
    {"char": "初", "pinyin": "chu", "tone": 1, "radical": "刀", "kangxi_strokes": 7, "simplified_strokes": 7, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "初始、初心、初见"},
    {"char": "善", "pinyin": "shan", "tone": 4, "radical": "口", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "金", "luck": "吉", "gender": "中", "meaning": "善良、妥善、与人为善"},

    # ── 木 ──
    {"char": "木", "pinyin": "mu", "tone": 4, "radical": "木", "kangxi_strokes": 4, "simplified_strokes": 4, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "树木、木质、质朴"},
    {"char": "林", "pinyin": "lin", "tone": 2, "radical": "木", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "木", "luck": "吉", "gender": "中", "meaning": "树林、丛林、茂盛"},
    {"char": "森", "pinyin": "sen", "tone": 1, "radical": "木", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "森林、繁盛、森严"},
    {"char": "柏", "pinyin": "bo", "tone": 2, "radical": "木", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "柏树、四季常青、坚贞"},
    {"char": "松", "pinyin": "song", "tone": 1, "radical": "木", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "松树、苍松、高洁长寿"},
    {"char": "桐", "pinyin": "tong", "tone": 2, "radical": "木", "kangxi_strokes": 10, "simplified_strokes": 10, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "梧桐、凤栖梧桐"},
    {"char": "桐", "pinyin": "tong", "tone": 2, "radical": "木", "kangxi_strokes": 10, "simplified_strokes": 10, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "梧桐、凤栖梧桐"},
    {"char": "楠", "pinyin": "nan", "tone": 2, "radical": "木", "kangxi_strokes": 13, "simplified_strokes": 13, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "楠木、珍贵、坚实"},
    {"char": "楷", "pinyin": "kai", "tone": 3, "radical": "木", "kangxi_strokes": 13, "simplified_strokes": 13, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "楷模、榜样、楷书"},
    {"char": "栋", "pinyin": "dong", "tone": 4, "radical": "木", "kangxi_strokes": 12, "simplified_strokes": 9, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "栋梁、栋宇、国之栋梁"},
    {"char": "梁", "pinyin": "liang", "tone": 2, "radical": "木", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "栋梁、桥梁、人才"},
    {"char": "梓", "pinyin": "zi", "tone": 3, "radical": "木", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "木", "luck": "吉", "gender": "中", "meaning": "梓树、故乡、梓匠"},
    {"char": "杉", "pinyin": "shan", "tone": 1, "radical": "木", "kangxi_strokes": 7, "simplified_strokes": 7, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "杉木、挺拔、直上云霄"},
    {"char": "柯", "pinyin": "ke", "tone": 1, "radical": "木", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "枝柯、法则"},
    {"char": "榕", "pinyin": "rong", "tone": 2, "radical": "木", "kangxi_strokes": 14, "simplified_strokes": 14, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "榕树、繁荣、荫庇"},
    {"char": "芷", "pinyin": "zhi", "tone": 3, "radical": "艹", "kangxi_strokes": 10, "simplified_strokes": 7, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "白芷、香草、品行高洁"},
    {"char": "芸", "pinyin": "yun", "tone": 2, "radical": "艹", "kangxi_strokes": 10, "simplified_strokes": 7, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "芸香、芸芸众生"},
    {"char": "萱", "pinyin": "xuan", "tone": 1, "radical": "艹", "kangxi_strokes": 15, "simplified_strokes": 12, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "萱草、忘忧、母亲花"},
    {"char": "薇", "pinyin": "wei", "tone": 1, "radical": "艹", "kangxi_strokes": 19, "simplified_strokes": 16, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "蔷薇、薇草、清雅"},
    {"char": "蕊", "pinyin": "rui", "tone": 3, "radical": "艹", "kangxi_strokes": 18, "simplified_strokes": 15, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "花蕊、蕊心、美好"},
    {"char": "菲", "pinyin": "fei", "tone": 1, "radical": "艹", "kangxi_strokes": 14, "simplified_strokes": 11, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "芳菲、菲菲、芬芳"},
    {"char": "茗", "pinyin": "ming", "tone": 2, "radical": "艹", "kangxi_strokes": 12, "simplified_strokes": 9, "wuxing": "木", "luck": "吉", "gender": "中", "meaning": "茶茗、品茗、清雅"},
    {"char": "若", "pinyin": "ruo", "tone": 4, "radical": "艹", "kangxi_strokes": 11, "simplified_strokes": 8, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "若水、如若、虚怀若谷"},
    {"char": "茂", "pinyin": "mao", "tone": 4, "radical": "艹", "kangxi_strokes": 11, "simplified_strokes": 8, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "茂盛、茂密、繁茂"},
    {"char": "蔚", "pinyin": "wei", "tone": 4, "radical": "艹", "kangxi_strokes": 17, "simplified_strokes": 14, "wuxing": "木", "luck": "吉", "gender": "中", "meaning": "蔚蓝、蔚然、茂盛"},
    {"char": "蓝", "pinyin": "lan", "tone": 2, "radical": "艹", "kangxi_strokes": 20, "simplified_strokes": 13, "wuxing": "木", "luck": "吉", "gender": "女", "meaning": "蓝色、蓝田、蓝田生玉"},
    {"char": "萧", "pinyin": "xiao", "tone": 1, "radical": "艹", "kangxi_strokes": 19, "simplified_strokes": 11, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "萧瑟、潇洒、萧然"},
    {"char": "艺", "pinyin": "yi", "tone": 4, "radical": "艹", "kangxi_strokes": 21, "simplified_strokes": 4, "wuxing": "木", "luck": "吉", "gender": "中", "meaning": "艺术、技艺、多才多艺"},
    {"char": "荣", "pinyin": "rong", "tone": 2, "radical": "艹", "kangxi_strokes": 14, "simplified_strokes": 9, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "荣华、繁荣、欣欣向荣"},
    {"char": "华", "pinyin": "hua", "tone": 2, "radical": "艹", "kangxi_strokes": 14, "simplified_strokes": 6, "wuxing": "木", "luck": "吉", "gender": "男", "meaning": "华丽、光华、才华"},

    # ── 水 ──
    {"char": "水", "pinyin": "shui", "tone": 3, "radical": "水", "kangxi_strokes": 4, "simplified_strokes": 4, "wuxing": "水", "luck": "吉", "gender": "中", "meaning": "清水、上善若水"},
    {"char": "淼", "pinyin": "miao", "tone": 3, "radical": "水", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "水", "luck": "吉", "gender": "中", "meaning": "水大、浩淼、广阔"},
    {"char": "润", "pinyin": "run", "tone": 4, "radical": "水", "kangxi_strokes": 16, "simplified_strokes": 10, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "滋润、温润、润泽"},
    {"char": "泽", "pinyin": "ze", "tone": 2, "radical": "水", "kangxi_strokes": 17, "simplified_strokes": 8, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "恩泽、润泽、深仁厚泽"},
    {"char": "浩", "pinyin": "hao", "tone": 4, "radical": "水", "kangxi_strokes": 11, "simplified_strokes": 10, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "浩大、浩然、浩气长存"},
    {"char": "瀚", "pinyin": "han", "tone": 4, "radical": "水", "kangxi_strokes": 20, "simplified_strokes": 19, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "浩瀚、广大、瀚海"},
    {"char": "渊", "pinyin": "yuan", "tone": 1, "radical": "水", "kangxi_strokes": 12, "simplified_strokes": 11, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "深渊、学识渊博"},
    {"char": "清", "pinyin": "qing", "tone": 1, "radical": "水", "kangxi_strokes": 12, "simplified_strokes": 11, "wuxing": "水", "luck": "吉", "gender": "中", "meaning": "清澈、清正、清风明月"},
    {"char": "澜", "pinyin": "lan", "tone": 2, "radical": "水", "kangxi_strokes": 21, "simplified_strokes": 15, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "波澜、壮阔、推波助澜"},
    {"char": "溪", "pinyin": "xi", "tone": 1, "radical": "水", "kangxi_strokes": 14, "simplified_strokes": 13, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "溪水、溪流、清溪"},
    {"char": "涵", "pinyin": "han", "tone": 2, "radical": "水", "kangxi_strokes": 12, "simplified_strokes": 11, "wuxing": "水", "luck": "吉", "gender": "中", "meaning": "涵养、内涵、包涵"},
    {"char": "源", "pinyin": "yuan", "tone": 2, "radical": "水", "kangxi_strokes": 14, "simplified_strokes": 13, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "源头、源泉、饮水思源"},
    {"char": "流", "pinyin": "liu", "tone": 2, "radical": "水", "kangxi_strokes": 10, "simplified_strokes": 10, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "流水、源远流长"},
    {"char": "波", "pinyin": "bo", "tone": 1, "radical": "水", "kangxi_strokes": 9, "simplified_strokes": 8, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "波浪、推波、一波万波"},
    {"char": "沁", "pinyin": "qin", "tone": 4, "radical": "水", "kangxi_strokes": 8, "simplified_strokes": 7, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "沁人心脾、清新"},
    {"char": "湘", "pinyin": "xiang", "tone": 1, "radical": "水", "kangxi_strokes": 13, "simplified_strokes": 12, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "湘江、湘水、湖南"},
    {"char": "淳", "pinyin": "chun", "tone": 2, "radical": "水", "kangxi_strokes": 12, "simplified_strokes": 11, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "淳朴、淳厚、淳正"},
    {"char": "沛", "pinyin": "pei", "tone": 4, "radical": "水", "kangxi_strokes": 8, "simplified_strokes": 7, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "充沛、丰沛、精力旺盛"},
    {"char": "渤", "pinyin": "bo", "tone": 2, "radical": "水", "kangxi_strokes": 13, "simplified_strokes": 12, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "渤海、博大"},
    {"char": "泊", "pinyin": "bo", "tone": 2, "radical": "水", "kangxi_strokes": 9, "simplified_strokes": 8, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "淡泊、停泊、淡泊明志"},
    {"char": "潇", "pinyin": "xiao", "tone": 1, "radical": "水", "kangxi_strokes": 20, "simplified_strokes": 15, "wuxing": "水", "luck": "吉", "gender": "中", "meaning": "潇洒、潇潇、洒脱"},
    {"char": "洁", "pinyin": "jie", "tone": 2, "radical": "水", "kangxi_strokes": 16, "simplified_strokes": 9, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "洁净、纯洁、冰清玉洁"},
    {"char": "洛", "pinyin": "luo", "tone": 4, "radical": "水", "kangxi_strokes": 10, "simplified_strokes": 9, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "洛水、洛阳、洛神"},
    {"char": "洋", "pinyin": "yang", "tone": 2, "radical": "水", "kangxi_strokes": 10, "simplified_strokes": 9, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "海洋、广大、洋洋"},
    {"char": "汐", "pinyin": "xi", "tone": 1, "radical": "水", "kangxi_strokes": 7, "simplified_strokes": 6, "wuxing": "水", "luck": "吉", "gender": "女", "meaning": "潮汐、晚潮"},
    {"char": "渝", "pinyin": "yu", "tone": 2, "radical": "水", "kangxi_strokes": 13, "simplified_strokes": 12, "wuxing": "水", "luck": "吉", "gender": "中", "meaning": "重庆、矢志不渝"},
    {"char": "衍", "pinyin": "yan", "tone": 3, "radical": "行", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "繁衍、衍生、生生不息"},
    {"char": "泊", "pinyin": "bo", "tone": 2, "radical": "水", "kangxi_strokes": 9, "simplified_strokes": 8, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "淡泊、停泊、淡泊明志"},
    {"char": "沙", "pinyin": "sha", "tone": 1, "radical": "水", "kangxi_strokes": 8, "simplified_strokes": 7, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "沙粒、聚沙成塔"},
    {"char": "泉", "pinyin": "quan", "tone": 2, "radical": "水", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "水", "luck": "吉", "gender": "男", "meaning": "泉水、源泉、泉涌"},

    # ── 火 ──
    {"char": "火", "pinyin": "huo", "tone": 3, "radical": "火", "kangxi_strokes": 4, "simplified_strokes": 4, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "火焰、光明、热情"},
    {"char": "炎", "pinyin": "yan", "tone": 2, "radical": "火", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "炎炎、炎热、炎黄子孙"},
    {"char": "焱", "pinyin": "yan", "tone": 4, "radical": "火", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "火焰、光焰、焱飞"},
    {"char": "灿", "pinyin": "can", "tone": 4, "radical": "火", "kangxi_strokes": 17, "simplified_strokes": 7, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "灿烂、金光灿灿"},
    {"char": "煜", "pinyin": "yu", "tone": 4, "radical": "火", "kangxi_strokes": 13, "simplified_strokes": 13, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "照耀、光辉灿烂"},
    {"char": "炜", "pinyin": "wei", "tone": 3, "radical": "火", "kangxi_strokes": 13, "simplified_strokes": 8, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "光明、光辉、炜烨"},
    {"char": "炫", "pinyin": "xuan", "tone": 4, "radical": "火", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "炫目、光耀、炫彩"},
    {"char": "烁", "pinyin": "shuo", "tone": 4, "radical": "火", "kangxi_strokes": 19, "simplified_strokes": 9, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "闪烁、光亮、闪烁其辞"},
    {"char": "焕", "pinyin": "huan", "tone": 4, "radical": "火", "kangxi_strokes": 13, "simplified_strokes": 11, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "焕发、焕然一新"},
    {"char": "烽", "pinyin": "feng", "tone": 1, "radical": "火", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "烽火、烽烟"},
    {"char": "焰", "pinyin": "yan", "tone": 4, "radical": "火", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "火焰、气焰、光焰"},
    {"char": "耀", "pinyin": "yao", "tone": 4, "radical": "羽", "kangxi_strokes": 20, "simplified_strokes": 20, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "光耀、闪耀、光宗耀祖"},
    {"char": "明", "pinyin": "ming", "tone": 2, "radical": "日", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "光明、明智、光明正大"},
    {"char": "旭", "pinyin": "xu", "tone": 4, "radical": "日", "kangxi_strokes": 6, "simplified_strokes": 6, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "旭日、初升、朝气蓬勃"},
    {"char": "晨", "pinyin": "chen", "tone": 2, "radical": "日", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "早晨、晨光、晨曦"},
    {"char": "曦", "pinyin": "xi", "tone": 1, "radical": "日", "kangxi_strokes": 20, "simplified_strokes": 20, "wuxing": "火", "luck": "吉", "gender": "女", "meaning": "晨曦、阳光、曦光"},
    {"char": "晴", "pinyin": "qing", "tone": 2, "radical": "日", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "火", "luck": "吉", "gender": "女", "meaning": "晴朗、晴天、晴空万里"},
    {"char": "暖", "pinyin": "nuan", "tone": 3, "radical": "日", "kangxi_strokes": 13, "simplified_strokes": 13, "wuxing": "火", "luck": "吉", "gender": "女", "meaning": "温暖、暖阳、暖意"},
    {"char": "昕", "pinyin": "xin", "tone": 1, "radical": "日", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "黎明、昕旦、朝气"},
    {"char": "晖", "pinyin": "hui", "tone": 1, "radical": "日", "kangxi_strokes": 13, "simplified_strokes": 10, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "阳光、春晖、晖映"},
    {"char": "昭", "pinyin": "zhao", "tone": 1, "radical": "日", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "昭示、昭昭、昭明"},
    {"char": "晓", "pinyin": "xiao", "tone": 3, "radical": "日", "kangxi_strokes": 16, "simplified_strokes": 10, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "拂晓、知晓、晓畅"},
    {"char": "映", "pinyin": "ying", "tone": 4, "radical": "日", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "火", "luck": "吉", "gender": "女", "meaning": "映照、交相辉映"},
    {"char": "星", "pinyin": "xing", "tone": 1, "radical": "日", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "星辰、星光、吉星高照"},
    {"char": "彤", "pinyin": "tong", "tone": 2, "radical": "彡", "kangxi_strokes": 7, "simplified_strokes": 7, "wuxing": "火", "luck": "吉", "gender": "女", "meaning": "红色、彤云、彤霞"},
    {"char": "采", "pinyin": "cai", "tone": 3, "radical": "采", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "采撷、神采、风采"},
    {"char": "南", "pinyin": "nan", "tone": 2, "radical": "十", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "南方、南风、南国"},
    {"char": "德", "pinyin": "de", "tone": 2, "radical": "心", "kangxi_strokes": 15, "simplified_strokes": 15, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "品德、道德、厚德载物"},
    {"char": "乐", "pinyin": "le", "tone": 4, "radical": "木", "kangxi_strokes": 15, "simplified_strokes": 5, "wuxing": "火", "luck": "吉", "gender": "中", "meaning": "快乐、音乐、乐天知命"},
    {"char": "光", "pinyin": "guang", "tone": 1, "radical": "儿", "kangxi_strokes": 6, "simplified_strokes": 6, "wuxing": "火", "luck": "吉", "gender": "男", "meaning": "光明、光芒、光明正大"},

    # ── 土 ──
    {"char": "土", "pinyin": "tu", "tone": 3, "radical": "土", "kangxi_strokes": 3, "simplified_strokes": 3, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "土地、本土、厚土"},
    {"char": "坤", "pinyin": "kun", "tone": 1, "radical": "土", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "乾坤、坤厚载物、厚德"},
    {"char": "城", "pinyin": "cheng", "tone": 2, "radical": "土", "kangxi_strokes": 10, "simplified_strokes": 9, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "城池、城池坚固、众志成城"},
    {"char": "培", "pinyin": "pei", "tone": 2, "radical": "土", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "培养、栽培、培植"},
    {"char": "垣", "pinyin": "yuan", "tone": 2, "radical": "土", "kangxi_strokes": 9, "simplified_strokes": 9, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "城垣、星辰垣"},
    {"char": "坚", "pinyin": "jian", "tone": 1, "radical": "土", "kangxi_strokes": 11, "simplified_strokes": 7, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "坚定、坚强、坚如磐石"},
    {"char": "坦", "pinyin": "tan", "tone": 3, "radical": "土", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "平坦、坦然、坦荡"},
    {"char": "宇", "pinyin": "yu", "tone": 3, "radical": "宀", "kangxi_strokes": 6, "simplified_strokes": 6, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "宇宙、气宇轩昂、宇内"},
    {"char": "辰", "pinyin": "chen", "tone": 2, "radical": "辰", "kangxi_strokes": 7, "simplified_strokes": 7, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "星辰、良辰、良辰美景"},
    {"char": "安", "pinyin": "an", "tone": 1, "radical": "宀", "kangxi_strokes": 6, "simplified_strokes": 6, "wuxing": "土", "luck": "吉", "gender": "中", "meaning": "安定、平安、安居乐业"},
    {"char": "容", "pinyin": "rong", "tone": 2, "radical": "宀", "kangxi_strokes": 10, "simplified_strokes": 10, "wuxing": "土", "luck": "吉", "gender": "女", "meaning": "容貌、从容、雍容"},
    {"char": "宜", "pinyin": "yi", "tone": 2, "radical": "宀", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "中", "meaning": "适宜、宜人、宜室宜家"},
    {"char": "宛", "pinyin": "wan", "tone": 3, "radical": "宀", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "女", "meaning": "宛如、宛然、宛转"},
    {"char": "峥", "pinyin": "zheng", "tone": 1, "radical": "山", "kangxi_strokes": 11, "simplified_strokes": 9, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "峥嵘、不凡、岁月峥嵘"},
    {"char": "岚", "pinyin": "lan", "tone": 2, "radical": "山", "kangxi_strokes": 12, "simplified_strokes": 7, "wuxing": "土", "luck": "吉", "gender": "女", "meaning": "山岚、雾岚、岚气"},
    {"char": "岳", "pinyin": "yue", "tone": 4, "radical": "山", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "山岳、五岳、岳峙"},
    {"char": "峰", "pinyin": "feng", "tone": 1, "radical": "山", "kangxi_strokes": 10, "simplified_strokes": 10, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "山峰、顶峰、登峰造极"},
    {"char": "岩", "pinyin": "yan", "tone": 2, "radical": "山", "kangxi_strokes": 8, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "岩石、坚岩、千岩万壑"},
    {"char": "岭", "pinyin": "ling", "tone": 3, "radical": "山", "kangxi_strokes": 17, "simplified_strokes": 8, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "山岭、崇山峻岭"},
    {"char": "磊", "pinyin": "lei", "tone": 3, "radical": "石", "kangxi_strokes": 15, "simplified_strokes": 15, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "磊落、光明磊落"},
    {"char": "轩", "pinyin": "xuan", "tone": 1, "radical": "车", "kangxi_strokes": 10, "simplified_strokes": 7, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "气宇轩昂、轩窗、轩昂"},
    {"char": "远", "pinyin": "yuan", "tone": 3, "radical": "辶", "kangxi_strokes": 17, "simplified_strokes": 7, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "远大、深远、任重道远"},
    {"char": "维", "pinyin": "wei", "tone": 2, "radical": "糸", "kangxi_strokes": 14, "simplified_strokes": 11, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "维系、思维、维度"},
    {"char": "越", "pinyin": "yue", "tone": 4, "radical": "走", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "土", "luck": "吉", "gender": "男", "meaning": "超越、越过了不起"},
    {"char": "韵", "pinyin": "yun", "tone": 4, "radical": "音", "kangxi_strokes": 19, "simplified_strokes": 13, "wuxing": "土", "luck": "吉", "gender": "女", "meaning": "韵味、韵律、风韵"},
    {"char": "雅", "pinyin": "ya", "tone": 3, "radical": "隹", "kangxi_strokes": 12, "simplified_strokes": 12, "wuxing": "土", "luck": "吉", "gender": "女", "meaning": "高雅、文雅、雅致"},
    {"char": "婉", "pinyin": "wan", "tone": 3, "radical": "女", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "土", "luck": "吉", "gender": "女", "meaning": "温婉、婉转、婉约"},
    {"char": "意", "pinyin": "yi", "tone": 4, "radical": "心", "kangxi_strokes": 13, "simplified_strokes": 13, "wuxing": "土", "luck": "吉", "gender": "中", "meaning": "心意、意境、称心如意"},
    {"char": "恩", "pinyin": "en", "tone": 1, "radical": "心", "kangxi_strokes": 10, "simplified_strokes": 10, "wuxing": "土", "luck": "吉", "gender": "中", "meaning": "恩情、恩德、感恩"},
    {"char": "悠", "pinyin": "you", "tone": 1, "radical": "心", "kangxi_strokes": 11, "simplified_strokes": 11, "wuxing": "土", "luck": "吉", "gender": "中", "meaning": "悠然、悠远、悠长"},
]


def generate_char_db():
    """生成字库JSON文件"""
    # 去重（按汉字+拼音）
    seen = set()
    unique_chars = []
    for c in CHARS:
        key = (c["char"], c["pinyin"])
        if key not in seen:
            seen.add(key)
            unique_chars.append(c)

    # 按五行分组统计
    wuxing_count = {}
    for c in unique_chars:
        wx = c["wuxing"]
        wuxing_count[wx] = wuxing_count.get(wx, 0) + 1

    output = {
        "version": "1.0",
        "total": len(unique_chars),
        "wuxing_distribution": wuxing_count,
        "chars": unique_chars,
    }

    output_path = Path(__file__).parent.parent / "data" / "dict" / "chars.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"字库生成完成: {output_path}")
    print(f"总计 {len(unique_chars)} 字")
    print(f"五行分布: {wuxing_count}")


if __name__ == "__main__":
    generate_char_db()
