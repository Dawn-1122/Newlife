"""
起名偏好枚举常量（单一事实来源）

风格 / 寓意 / 行业 → 五行 的映射定义。
前端小程序无共享包，需在 `miniprogram/utils/api.js` 中镜像一份同名常量，
改动时两处需同步更新。

注意：这里的枚举均为「排序加权 / 预留透传」用途，不参与硬过滤，
避免「风格 + 寓意」双条件把候选集过滤到过小。
"""

# 风格枚举：code -> 中文名/优先来源/意象关键词/选字倾向
STYLE_OPTIONS = {
    "classic": {
        "name": "古风雅致",
        "source_preference": ["诗经", "楚辞", "汉魏古诗"],
        "imagery_keywords": ["风雅", "古典", "清雅", "雅正", "怀古"],
        "char_hint": "偏好玉/丝/木/水等雅致部首，笔画适中",
    },
    "modern": {
        "name": "现代简约",
        "source_preference": ["唐诗", "宋词"],
        "imagery_keywords": ["简约", "明快", "清新", "自然"],
        "char_hint": "偏好常用、笔画简洁、易读易写的字",
    },
    "grand": {
        "name": "大气沉稳",
        "source_preference": ["经史子集", "汉魏古诗"],
        "imagery_keywords": ["宏大", "沉稳", "家国", "志向", "山川"],
        "char_hint": "偏好笔画厚重、意象宏阔的字",
    },
    "fresh": {
        "name": "清新灵动",
        "source_preference": ["唐诗", "宋词", "诗经"],
        "imagery_keywords": ["灵动", "清新", "山水", "花木", "晨露"],
        "char_hint": "偏好草木/水/风等清新意象字",
    },
}

# 寓意枚举：code -> 中文名 + 匹配关键词（用于匹配 poetry.imagery/scene 与 chars.meaning）
MEANING_OPTIONS = {
    "wisdom":  {"name": "智慧", "keywords": ["智慧", "聪明", "博学", "睿智", "才思", "聪慧"]},
    "health":  {"name": "健康", "keywords": ["健康", "长寿", "康健", "安康", "松柏", "强健"]},
    "bravery": {"name": "勇敢", "keywords": ["勇敢", "坚毅", "刚强", "无畏", "勇毅", "果敢"]},
    "gentle":  {"name": "温婉", "keywords": ["温婉", "温柔", "娴静", "淑雅", "婉约", "柔美"]},
    "wealth":  {"name": "富贵", "keywords": ["富贵", "富足", "荣华", "昌盛", "丰裕", "兴旺"]},
    "peace":   {"name": "平安", "keywords": ["平安", "安宁", "祥和", "顺遂", "宁静", "安稳"]},
    "talent":  {"name": "才华", "keywords": ["才华", "文采", "才情", "聪颖", "才俊", "卓越"]},
    "virtue":  {"name": "品德", "keywords": ["品德", "德行", "仁德", "贤良", "高洁", "正直"]},
}

# 寓意最多选择个数
MEANING_MAX_SELECT = 3

# 行业 code -> 五行（成人改名/品牌店名 P1 使用，P0 仅定义常量并透传 industry 字段）
INDUSTRY_WUXING = {
    "tech":          "火",  # 互联网/科技/IT
    "media":         "火",  # 传媒/文创/设计
    "catering":      "火",  # 餐饮
    "energy":        "火",  # 能源
    "finance":       "金",  # 金融/财会/证券
    "law":           "金",  # 法律
    "manufacturing": "金",  # 制造/工业/五金
    "education":     "木",  # 教育/文化/出版
    "medical":       "木",  # 医疗/健康
    "art":           "木",  # 艺术
    "agriculture":   "木",  # 农业
    "realestate":    "土",  # 地产/建筑/工程
    "trade":         "水",  # 贸易/物流/航运
    "tourism":       "水",  # 旅游/服务
}
