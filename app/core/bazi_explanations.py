"""
八字命理解释数据

为五行、十天干、十二地支、四柱位、用神提供通俗易懂的命理解释，
用于前端「八字详解」页展示，让用户理解八字排盘背后的含义。

参考：《子平真诠》《渊海子平》《三命通会》等传统命理典籍，
以通俗化语言呈现，非严肃命理推算。
"""

# ── 五行解释 ──

WUXING_EXPLANATIONS = {
    "金": {
        "nature": "主义",
        "direction": "西方",
        "season": "秋季",
        "color": "白",
        "organ": "肺、大肠",
        "brief": "刚毅果决，肃杀收敛",
        "detail": "金曰从革，主「义」，其性刚，其情烈。象征刚毅、果断、变革与肃杀，如刀剑之利、珠玉之坚。金旺者果敢坚毅、重义气，但过刚易折，宜以水润之、以火炼之。",
    },
    "木": {
        "nature": "主仁",
        "direction": "东方",
        "season": "春季",
        "color": "青",
        "organ": "肝、胆",
        "brief": "生发向上，仁德温和",
        "detail": "木曰曲直，主「仁」，其性直，其情和。象征生长、升发、条达与仁爱，如树木之挺拔、藤蔓之柔韧。木旺者仁慈温和、有上进心，但过旺则易固执己见。",
    },
    "水": {
        "nature": "主智",
        "direction": "北方",
        "season": "冬季",
        "color": "黑",
        "organ": "肾、膀胱",
        "brief": "聪慧灵动，润下含蓄",
        "detail": "水曰润下，主「智」，其性聪，其情善。象征智慧、流动、包容与润泽，如江河之奔流、雨露之无声。水旺者聪明机智、善于变通，但过旺则易心性漂泊、想法多变。",
    },
    "火": {
        "nature": "主礼",
        "direction": "南方",
        "season": "夏季",
        "color": "赤",
        "organ": "心、小肠",
        "brief": "热情有礼，光明向上",
        "detail": "火曰炎上，主「礼」，其性急，其情恭。象征热情、光明、文明与礼仪，如太阳之普照、灯烛之温暖。火旺者热情大方、有礼有节，但过旺则易急躁冒进。",
    },
    "土": {
        "nature": "主信",
        "direction": "中央",
        "season": "长夏",
        "color": "黄",
        "organ": "脾、胃",
        "brief": "厚重诚信，承载万物",
        "detail": "土爰稼穑，主「信」，其性重，其情厚。象征稳重、包容、诚信与承载，如大地之厚德、田园之滋养。土旺者忠厚守信、稳重踏实，但过旺则易保守、缺少变通。",
    },
}

# ── 天干解释 ──

TIANGAN_EXPLANATIONS = {
    "甲": {"yinyang": "阳", "wuxing": "木", "brief": "参天大树，栋梁之材", "detail": "甲为阳木，如参天大树，主仁德、正直，有担当、向上生长之象。"},
    "乙": {"yinyang": "阴", "wuxing": "木", "brief": "花草藤萝，柔韧灵秀", "detail": "乙为阴木，如花草藤萝，主温和、柔顺，有婉转、善于协调之象。"},
    "丙": {"yinyang": "阳", "wuxing": "火", "brief": "太阳之火，光明磊落", "detail": "丙为阳火，如烈日当空，主热情、光明，有开朗、照亮他人之象。"},
    "丁": {"yinyang": "阴", "wuxing": "火", "brief": "灯烛之火，温暖细腻", "detail": "丁为阴火，如灯烛星火，主温和、细腻，有内敛、润物无声之象。"},
    "戊": {"yinyang": "阳", "wuxing": "土", "brief": "城墙之土，稳重厚实", "detail": "戊为阳土，如高山城墙，主诚信、稳重，有承载、守护一方之象。"},
    "己": {"yinyang": "阴", "wuxing": "土", "brief": "田园之土，滋养万物", "detail": "己为阴土，如田园沃土，主包容、细腻，有滋养、默默奉献之象。"},
    "庚": {"yinyang": "阳", "wuxing": "金", "brief": "刀剑之金，刚硬锋利", "detail": "庚为阳金，如刀剑矿金，主刚毅、果断，有锐利、雷厉风行之象。"},
    "辛": {"yinyang": "阴", "wuxing": "金", "brief": "珠玉之金，精致华贵", "detail": "辛为阴金，如珠玉首饰，主精致、敏锐，有清秀、追求完美之象。"},
    "壬": {"yinyang": "阳", "wuxing": "水", "brief": "江河之水，奔流不息", "detail": "壬为阳水，如江河湖海，主聪慧、豁达，有气度、海纳百川之象。"},
    "癸": {"yinyang": "阴", "wuxing": "水", "brief": "雨露之水，润物无声", "detail": "癸为阴水，如雨露甘霖，主柔韧、智慧，有细腻、潜移默化之象。"},
}

# ── 地支解释 ──

DIZHI_EXPLANATIONS = {
    "子": {"yinyang": "阳", "wuxing": "水", "shengxiao": "鼠", "brief": "智慧灵动，生机初萌", "detail": "子为阳水，十二地支之首，藏癸水。象征智慧、灵动与万物初生的萌动。"},
    "丑": {"yinyang": "阴", "wuxing": "土", "shengxiao": "牛", "brief": "稳重踏实，默默耕耘", "detail": "丑为阴土，藏己土、癸水、辛金。象征稳重、踏实与默默积累的力量。"},
    "寅": {"yinyang": "阳", "wuxing": "木", "shengxiao": "虎", "brief": "生机勃勃，勇猛进取", "detail": "寅为阳木，藏甲木、丙火、戊土。象征生机、勇猛与春日勃发的朝气。"},
    "卯": {"yinyang": "阴", "wuxing": "木", "shengxiao": "兔", "brief": "柔顺温和，灵动秀美", "detail": "卯为阴木，藏乙木。象征柔顺、温和与清新灵秀的气质。"},
    "辰": {"yinyang": "阳", "wuxing": "土", "shengxiao": "龙", "brief": "包容大气，蓄势待发", "detail": "辰为阳土，藏戊土、乙木、癸水。象征包容、大气与潜藏的腾飞之势。"},
    "巳": {"yinyang": "阴", "wuxing": "火", "shengxiao": "蛇", "brief": "机敏智慧，变化多端", "detail": "巳为阴火，藏丙火、庚金、戊土。象征机敏、智慧与灵活善变的能力。"},
    "午": {"yinyang": "阳", "wuxing": "火", "shengxiao": "马", "brief": "热情奔放，光明磊落", "detail": "午为阳火，藏丁火、己土。象征热情、奔放与如日中天的光明。"},
    "未": {"yinyang": "阴", "wuxing": "土", "shengxiao": "羊", "brief": "温厚和善，滋养包容", "detail": "未为阴土，藏己土、丁火、乙木。象征温厚、和善与滋养包容的品性。"},
    "申": {"yinyang": "阳", "wuxing": "金", "shengxiao": "猴", "brief": "机敏灵活，刚健有为", "detail": "申为阳金，藏庚金、壬水、戊土。象征机敏、灵活与刚健果断的行动力。"},
    "酉": {"yinyang": "阴", "wuxing": "金", "shengxiao": "鸡", "brief": "精致刚毅，锋芒内敛", "detail": "酉为阴金，藏辛金。象征精致、刚毅与含蓄内敛的锋芒。"},
    "戌": {"yinyang": "阳", "wuxing": "土", "shengxiao": "狗", "brief": "忠诚守信，守护担当", "detail": "戌为阳土，藏戊土、辛金、丁火。象征忠诚、守信与守护担当的责任感。"},
    "亥": {"yinyang": "阴", "wuxing": "水", "shengxiao": "猪", "brief": "包容豁达，蓄藏生发", "detail": "亥为阴水，藏壬水、甲木。象征包容、豁达与蓄势待发的生机。"},
}

# ── 四柱位解释 ──

PILLAR_EXPLANATIONS = {
    "year": {"name": "年柱", "meaning": "代表祖上、父母与早年运势，象征一个人的根基与出身。"},
    "month": {"name": "月柱", "meaning": "代表父母、兄弟与青年时期，象征成长环境与事业开端。"},
    "day": {"name": "日柱", "meaning": "代表自身与配偶，日干为「日主」，是命局的核心。"},
    "hour": {"name": "时柱", "meaning": "代表子女与晚年运势，象征人生的归宿与结局。"},
}

# ── 藏干层级标签 ──

CANGGAN_LEVELS = ["本气", "中气", "余气"]

# ── 用神判定的解释模板 ──

def build_xiyong_explanation(xiyong: dict) -> str:
    """根据喜用神判定结果，生成通俗解释"""
    day_master = xiyong["day_master"]
    day_master_wx = xiyong["day_master_wuxing"]
    strength_label = xiyong["strength_label"]
    strength_ratio = xiyong["strength_ratio"]
    xi_wuxing = xiyong["xi_wuxing"]
    yong_wuxing = xiyong["yong_wuxing"]
    ji_wuxing = xiyong["ji_wuxing"]

    parts = []
    parts.append(
        f"日主为「{day_master}」五行属{day_master_wx}。"
        f"日主（代表自己）的力量在命局中占比约{strength_ratio}%，属于「{strength_label}」。"
    )

    if strength_label == "身强":
        parts.append(
            f"身强者宜用克、泄、耗来平衡，因此喜用五行宜取"
            f"{'、'.join(xi_wuxing)}，其中以{yong_wuxing}为用神（最有力）。"
        )
    else:
        parts.append(
            f"身弱者宜用生、扶来补益，因此喜用五行宜取"
            f"{'、'.join(xi_wuxing)}，其中以{yong_wuxing}为用神（最得力）。"
        )

    if ji_wuxing:
        parts.append(f"忌神为{'、'.join(ji_wuxing)}，起名时应尽量避开或减少这些五行。")
    else:
        parts.append("此命局五行较为均衡，无明显忌神。")

    return "".join(parts)
