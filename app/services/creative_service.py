"""
创意起名服务（网名昵称 / 宠物 / 商业）

覆盖 xmind 架构「起名」大类下、除宝宝起名外的全部能力：
- 网名昵称三细分：平台名称 / 游戏昵称 / 虚构角色
- 宠物起名
- 商业名称（店名 · 品牌 · 字号）

设计原则：
1. **离线可用**：本地词库 + 组合逻辑即可产出，不依赖 LLM（`.env` 未配置时照常工作）。
2. **单一事实来源**：词库集中在 `CREATIVE_BANKS`，kind 枚举在 `CREATIVE_KINDS`；
   前端 `miniprogram/utils/api.js` 镜像 kind 枚举，改动时两处同步。
3. **确定性**：以 (kind, keywords, pet_type, gender, industry) 为随机种子，
   同一输入同一结果，刷新不跳变、测试可断言。
4. **LLM 增强预留**：返回结构已含 `reason` 字段，未来有配置时可在 `generate` 末尾
   用 `LLMService` 覆盖 reason / 追加生成，不改前端契约。
"""

import hashlib
import random
import re
from typing import Optional

from app.core.config import settings
from app.core.naming_options import INDUSTRY_WUXING
from app.services.llm_service import LLMError, LLMService

# 创意起名 kind 枚举（前端 api.js 需镜像）
CREATIVE_KINDS = ("platform", "game", "role", "pet", "business")

# 各 kind 的中文名（前端标题 / reason 里用）
KIND_NAMES = {
    "platform": "平台名称",
    "game": "游戏昵称",
    "role": "虚构角色",
    "pet": "宠物起名",
    "business": "商业名称",
}

# ── 词库（单一事实来源） ──
# 词条均为「意象/名词」，组合逻辑见各生成函数。整体遵循：
# 积极、雅致、不碰低俗/宗教/历史原型专名（伦理底线同宝宝起名）。

CREATIVE_BANKS = {
    # 平台名称：意象词（基底） + 状态/动作结尾（后缀），如「山樱」+「慢焙」= 山樱慢焙
    "platform_bases": [
        "山樱", "雾岛", "纸间", "苔原", "棱镜", "云履", "褶皱", "灯下", "窗边",
        "露台", "深夜", "天文台", "渡口", "邮局", "鲸落", "星野", "松风", "云影",
        "竹露", "苔痕", "光合", "咖啡因", "慢递", "手账", "明信片", "时雨", "初雪",
        "远山", "流萤", "清泉", "月台", "晨雾", "海盐", "茶歇", "旧巷", "渡鸦",
    ],
    "platform_suffixes": [
        "收集所", "停泊中", "慢焙", "观察站", "未校准", "在逃", "编辑中", "存档中",
        "未命名", "缓冲区", "观测站", "研究日志", "修理中", "营业中", "迟归",
        "观测记录", "收藏夹", "备忘录", "放映室", "茶水间", "手记", "邮差", "寻呼",
    ],
    # 平台专属词库（platform_type 指定时用；未指定回退 platform_bases/suffixes）。
    # 小红书复用通用库（自然意象 + 生活肌理，见上）。
    "platform_bases_zhihu": ["接口", "拓扑", "热力学", "现象学", "温湿度", "剂量", "编码", "病理", "场论", "算法"],
    "platform_suffixes_zhihu": ["未报错", "煮面中", "观测站", "未校准", "待验证", "笔记", "在岗", "未定义"],
    "platform_bases_douyin": ["今天也在", "深夜还在", "凌晨", "下班后", "周末", "雨天"],
    "platform_suffixes_douyin": ["修空调", "搬砖", "营业", "整活", "做菜", "遛狗", "存钱", "搞钱"],
    "platform_bases_bili": ["404", "编译", "次元", "弹幕", "番剧", "中二", "像素", "幽灵"],
    "platform_suffixes_bili": ["NotFound但心动", "成功·心跳", "加载中", "破壁", "觉醒", "附身", "转生", "走位"],
    "platform_bases_wechat": ["林工", "苏律师", "陈医生", "王老师", "李会计", "周码农", "吴设计", "郑记者"],
    "platform_suffixes_wechat": ["·光伏在逃焊工", "·合同里找糖", "·夜班中", "·批作业中", "·对账中", "·改稿中", "·在现场", "·搬砖中"],

    # 游戏昵称：意象核（2 字）+ 状态尾（2 字），如「霜痕」+「未晞」= 霜痕未晞
    "game_nuclei": [
        "霜痕", "烬海", "雷动", "焰心", "渊面", "风息", "星屑", "尘嚣", "影渊",
        "蚀骨", "淬锋", "雾隐", "岚起", "潮信", "岩扉", "曜灵", "冥火", "光年",
        "暗潮", "苍羽", "玄冰", "赤霄", "紫电", "残阳", "流火", "折镜", "天裂",
    ],
    "game_tails": [
        "未晞", "回响", "断刃", "静滞", "零帧", "悬置", "残响", "行歌", "载入",
        "判决", "纪元", "挽歌", "归途", "无赦", "碎镜", "重燃", "弥留", "拾荒",
        "折返", "未卜", "归墟", "燃尽", "无眠", "长夜", "余烬", "归鞘",
    ],
    # 游戏类型专属词库（game_type 指定时用；未指定回退 game_nuclei/tails）
    "game_scifi_nuclei": ["熵减", "琥珀纪", "星港", "跃迁", "奇点", "轨道", "曲率", "维度", "脉冲", "坐标"],
    "game_scifi_tails": ["观测员", "存档", "协议", "日志", "未抵达", "偏移", "静默", "回响", "过载", "待命"],
    "game_tactical_nuclei": ["弹道", "温控", "战术", "火力", "精度", "防线", "侦查", "压制", "突袭", "狙击"],
    "game_tactical_tails": ["修正", "协议", "部署", "在岗", "锁定", "待命", "零点", "收束", "校准", "推进"],
    "game_casual_nuclei": ["好感度", "收成", "工坊", "客栈", "菜园", "钓鱼", "咖啡", "烘焙", "花园", "牧场"],
    "game_casual_tails": ["阈值", "满仓", "营业中", "今日份", "养成中", "攻略", "日记", "日常", "加点", "存档"],
    # 游戏机制语汇：与用户「职业/身份」关键词组合（职业×游戏机制双轨，如「温控」+「协议」）
    "game_mech_tails": ["协议", "加点", "存档", "阈值", "观测员", "校准", "部署", "未加载", "待命", "v2.3.1", "DLC已加载", "攻略中"],

    # 虚构角色：中式「姓 + 名」为主，另附代号式（供设定/代号场景）
    "role_surnames": [
        "沈", "林", "顾", "苏", "陆", "温", "谢", "江", "秦", "白", "叶", "云",
        "慕", "迟", "闻", "时", "宋", "楚", "裴", "萧", "许", "程", "黎", "祝",
    ],
    "role_given": [
        "砚白", "昭默", "青梧", "之恒", "云鹤", "景行", "修远", "承砚", "明枢",
        "望舒", "青黛", "未晞", "扶苏", "采薇", "南絮", "芷若", "听澜", "疏影",
        "晚棠", "知微", "清和", "亦舒", "怀瑾", "叙白", "鹤归", "砚秋",
    ],
    # 按性别分库（gender 指定时用）；未指定回退中性 role_given
    "role_given_male": [
        "砚白", "昭默", "青梧", "之恒", "云鹤", "景行", "修远", "承砚", "明枢",
        "怀瑾", "叙白", "鹤归", "砚秋", "凌云", "承泽", "景铄", "泽川", "亦清",
    ],
    "role_given_female": [
        "青黛", "未晞", "扶苏", "采薇", "南絮", "芷若", "听澜", "疏影",
        "晚棠", "知微", "清和", "亦舒", "望舒", "若汐", "云舒", "初雪",
        "清欢", "落微", "凝霜",
    ],
    # 单字性别气质字（与类型核 / 性格字组合成三字名，突出男女气质）
    "role_male_chars": ["昭", "砚", "鹤", "岳", "辰", "衡", "启", "承", "铭", "朔", "毅", "峥", "凌", "川", "泽", "峻"],
    "role_female_chars": ["黛", "薇", "棠", "芷", "疏", "汐", "璃", "婉", "清", "芙", "笙", "瑶", "柔", "雪", "初", "凝"],
    "role_codes": [
        "守阈者", "契文使", "夜巡·零", "静默·观测", "归墟引渡人", "燃灯者",
        "摘星人", "织梦师", "摆渡人", "观棋者", "守夜人", "解铃人", "燃烛", "拾光者",
    ],

    # 宠物：食物系 / 形态叠词系 / 吉祥系
    "pet_food": [
        "汤圆", "糯米", "年糕", "豆沙", "麻薯", "布丁", "拿铁", "摩卡", "芝麻",
        "花生", "糖豆", "蛋挞", "芋圆", "栗子", "团子", "奶茶", "雪顶", "红豆",
        "小笼", "奶盖", "芝麻糊",
    ],
    "pet_form": [
        "团团", "球球", "滚滚", "小煤球", "雪球", "胖达", "毛毛", "豆豆", "米粒",
        "小圆", "大橘", "黑糖", "小白", "斑斑", "点点", "小脚", "奶黄",
    ],
    "pet_bless": [
        "福宝", "来福", "招财", "平安", "富贵", "旺财", "如意", "元宝", "顺顺",
        "安安", "康康", "吉祥", "喜乐", "圆满", "安和",
    ],
    "pet_type_extra": {
        "cat": ["咪咪", "大橘", "奶猫", "阿橘", "鱼丸", "喵崽"],
        "dog": ["大黄", "阿黄", "黑子", "二狗", "铁柱", "旺仔"],
        "other": ["小乖", "嘟嘟", "皮皮", "果冻", "泡泡", "小满"],
    },

    # 商业名称：吉字（两字名 = 吉+吉；三字名 = 吉+吉+字号后缀）
    "biz_ausp": [
        "瑞", "祥", "泰", "和", "盛", "昌", "隆", "兴", "丰", "聚", "德", "诚",
        "恒", "源", "荣", "福", "吉", "康", "顺", "达", "嘉", "锦", "晟", "衡",
    ],
    "biz_suffix": [
        "堂", "斋", "轩", "阁", "坊", "居", "记", "号", "行", "馆", "舍", "铺", "楼",
    ],
}

# ── 虚拟人物：小说类型 + 性格特征（单一事实来源，前端 api.js 镜像） ──
# 小说类型参考主流网络小说平台（起点/番茄/晋江）分类；nuclei 为该类型「世界观底色」意象核字，
# 用于与性格气质字组合成「姓 + 名」。整体遵循积极、雅致、不碰低俗/宗教/历史原型专名。

NOVEL_GENRES = [
    {"code": "xuanhuan", "name": "玄幻", "nuclei": ["玄", "昊", "辰", "苍", "渊", "冥", "荒", "穹", "曜", "焱", "霆", "霄"]},
    {"code": "xianxia", "name": "仙侠", "nuclei": ["剑", "云", "仙", "灵", "道", "凌", "羽", "霜", "御", "青", "星", "月"]},
    {"code": "wuxia", "name": "武侠", "nuclei": ["侠", "风", "刀", "剑", "义", "萧", "尘", "岳", "浪", "客", "孤", "影"]},
    {"code": "dushi", "name": "都市", "nuclei": ["城", "澜", "景", "川", "墨", "泽", "宁", "楚", "然", "熙", "凡", "尘"]},
    {"code": "kehuan", "name": "科幻", "nuclei": ["星", "宇", "光", "时", "空", "辰", "恒", "纪", "极", "维", "遥", "冥"]},
    {"code": "lishi", "name": "历史", "nuclei": ["谋", "策", "昭", "承", "启", "弘", "渊", "邦", "衡", "铭", "肃", "徵"]},
    {"code": "junshi", "name": "军事", "nuclei": ["锋", "锐", "戈", "岳", "征", "铁", "城", "疆", "骁", "策", "峙", "战"]},
    {"code": "xuanyi", "name": "悬疑灵异", "nuclei": ["幽", "冥", "晦", "谜", "隐", "缄", "夜", "雾", "玄", "寂", "墨", "岚"]},
    {"code": "youxi", "name": "游戏竞技", "nuclei": ["曜", "锋", "决", "燃", "竞", "岚", "刃", "飒", "弈", "胜", "驰", "锐"]},
    {"code": "erciyuan", "name": "二次元", "nuclei": ["樱", "星", "梦", "璃", "汐", "千", "奈", "月", "光", "音", "晓", "瞳"]},
    {"code": "yanqing", "name": "言情", "nuclei": ["瑾", "婉", "思", "慕", "柔", "汐", "念", "暖", "霖", "安", "遥", "初"]},
    {"code": "qihuan", "name": "奇幻", "nuclei": ["灵", "晶", "焰", "霜", "影", "幻", "秘", "曜", "幽", "星", "辉", "翼"]},
    {"code": "moshi", "name": "末世", "nuclei": ["烬", "荒", "孤", "朔", "寂", "霜", "刃", "夜", "霆", "野", "铁", "风"]},
]

# 性格特征（人物气质）；atoms 为气质字，与类型核字组合成「姓 + 名」。
CHARACTER_TRAITS = [
    {"code": "qingleng", "name": "清冷", "atoms": ["白", "寒", "素", "霜", "雪", "月", "冰", "寂"]},
    {"code": "wenrun", "name": "温润", "atoms": ["玉", "暖", "和", "润", "熙", "沐", "柔", "安"]},
    {"code": "fuhei", "name": "腹黑", "atoms": ["墨", "玄", "暗", "策", "谋", "隐", "藏", "深"]},
    {"code": "aojiao", "name": "傲娇", "atoms": ["骄", "傲", "矜", "倔", "颖", "俏", "烈"]},
    {"code": "yangguang", "name": "阳光", "atoms": ["阳", "明", "朗", "灿", "曜", "晴", "燃", "暖"]},
    {"code": "lengjun", "name": "冷峻", "atoms": ["冷", "峻", "寒", "肃", "凛", "锐", "锋", "峭"]},
    {"code": "wenrou", "name": "温柔", "atoms": ["柔", "婉", "软", "和", "暖", "绵", "静", "安"]},
    {"code": "satuo", "name": "洒脱", "atoms": ["逸", "纵", "舒", "放", "云", "风", "野", "遥"]},
    {"code": "guao", "name": "孤傲", "atoms": ["孤", "傲", "独", "冷", "寒", "霜", "影", "寂"]},
    {"code": "chenwen", "name": "沉稳", "atoms": ["沉", "稳", "恒", "厚", "笃", "深", "渊", "岳"]},
    {"code": "rexue", "name": "热血", "atoms": ["燃", "烈", "焰", "炽", "勇", "战", "锋", "昂"]},
    {"code": "jiaoxie", "name": "狡黠", "atoms": ["黠", "灵", "慧", "俏", "机", "敏", "巧", "颖"]},
    {"code": "jianyi", "name": "坚毅", "atoms": ["坚", "毅", "韧", "刚", "恒", "笃", "铮", "铁"]},
    {"code": "lanyang", "name": "慵懒", "atoms": ["慵", "闲", "缓", "迟", "眠", "松", "宁"]},
    {"code": "shenmi", "name": "神秘", "atoms": ["玄", "幽", "隐", "秘", "冥", "邃", "谜", "岚"]},
]

# ── 平台名称：按「平台基因」分库（单一事实来源，前端 api.js 镜像） ──
# 小红书=自然意象+生活肌理；知乎=术语+自嘲专业感；抖音=口语张力；B站=梗+次元；微信=职业+真实感。
PLATFORM_TYPES = [
    {"code": "xiaohongshu", "name": "小红书"},
    {"code": "zhihu", "name": "知乎"},
    {"code": "douyin", "name": "抖音"},
    {"code": "bilibili", "name": "B站"},
    {"code": "wechat", "name": "微信"},
]

# ── 游戏昵称：按「游戏类型」分库（单一事实来源，前端 api.js 镜像） ──
# 仙侠奇幻=元素+意象+留白（原神风）；科幻=诗学；硬核战术=战术；休闲经营=经营。
GAME_TYPES = [
    {"code": "fantasy", "name": "仙侠奇幻"},
    {"code": "scifi", "name": "科幻"},
    {"code": "tactical", "name": "硬核战术"},
    {"code": "casual", "name": "休闲经营"},
]

# 商业：行业 → 取名侧重点（用于 reason 文案，不参与硬过滤）
INDUSTRY_HINT = {
    "tech": "取「新、锐、通达」之意，利科技感",
    "media": "取「传、达、华」之意，利传播声量",
    "catering": "取「丰、聚、香」之意，利人气与口碑",
    "energy": "取「盛、恒、源」之意，利长久动能",
    "finance": "取「诚、信、稳」之意，利信赖感",
    "law": "取「正、衡、信」之意，利公信力",
    "manufacturing": "取「精、固、成」之意，利品质感",
    "education": "取「德、学、成」之意，利育人之道",
    "medical": "取「康、和、仁」之意，利健康关怀",
    "art": "取「雅、韵、华」之意，利审美格调",
    "agriculture": "取「丰、源、生」之意，利丰饶气象",
    "realestate": "取「安、固、盛」之意，利稳重建基",
    "trade": "取「通、达、顺」之意，利流通往来",
    "tourism": "取「游、悦、和」之意，利宾至如归",
}


# ── LLM 增强（虚拟人物自定义描述，看广告解锁） ──
_ROLE_LLM_SYSTEM = (
    "你是资深网络小说人设命名专家，擅长为虚构角色起「有来历、可展开」的中文名。"
    "只输出合法 JSON，不输出任何解释文字。"
)


def _seed(*parts) -> int:
    """把输入拼成稳定整数种子（确定性）。"""
    raw = "|".join(str(p) for p in parts if p is not None)
    return int(hashlib.md5(raw.encode("utf-8")).hexdigest()[:8], 16)


def _shuffled(pool, seed, n=None):
    """按种子打乱并截断（不修改原列表）。"""
    rng = random.Random(seed)
    items = list(pool)
    rng.shuffle(items)
    return items if n is None else items[:n]


def _tokenize(keywords: str) -> list[str]:
    """把自由输入拆成 2-6 字的有效词块（去掉纯标点/数字/超长）。"""
    if not keywords:
        return []
    parts = re.split(r"[，,、\s;；/|]+", keywords.strip())
    out = []
    for p in parts:
        p = p.strip()
        if 1 <= len(p) <= 6 and not p.isdigit():
            out.append(p)
    return out[:4]


def _compose(bases, suffixes, count, seed):
    """基 × 后缀错位配对，保证基底与后缀都变化（避免同一基底连续出现）。"""
    b = _shuffled(bases, seed)
    s = _shuffled(suffixes, seed + 1)
    out, seen = [], set()
    n = min(len(b), len(s))
    # 第一轮：同位配对
    for i in range(n):
        name = f"{b[i]}{s[i]}"
        if name not in seen:
            seen.add(name)
            out.append(name)
        if len(out) >= count:
            return out
    # 第二轮：错位配对，补足到 count
    for i in range(n):
        name = f"{b[i]}{s[(i + 1) % n]}"
        if name not in seen:
            seen.add(name)
            out.append(name)
        if len(out) >= count:
            return out
    return out


# 平台调性描述（reason 文案用，key 对应 PLATFORM_TYPES 的 name）
_PLATFORM_FLAVOR = {
    "小红书": "自然意象、生活肌理",
    "知乎": "术语感、自嘲式专业",
    "抖音": "口语张力、记忆锚点",
    "B站": "有梗、次元穿透",
    "微信": "真实感、职业辨识度",
}


def _reason(kind, name, ctx) -> str:
    """给出一条简短、不空泛的「为什么适合」文案。"""
    kw = ctx.get("keywords")
    if kind == "platform":
        p_name = ctx.get("platform_name")
        base = f"贴合「{kw[0]}」的定位，" if kw else ""
        if p_name:
            flavor = _PLATFORM_FLAVOR.get(p_name, "有调性")
            return f"{base}{p_name}调性：{flavor}，好记也耐读"
        return f"{base}意象克制、留有生活肌理，好记也耐读"
    if kind == "game":
        g_name = ctx.get("game_name")
        if g_name:
            return f"{g_name}风格：意象与机制语汇交织，辨识度高、社区二创友好"
        return "意象与机制语汇交织，辨识度高、社区二创友好"
    if kind == "role":
        g_name = ctx.get("genre_name")
        t_name = ctx.get("trait_name")
        if g_name or t_name:
            flavor = " · ".join(p for p in (g_name, t_name) if p)
            return f"{flavor}底色下的名字：读来有来历，可作人设展开的支点"
        return "名中有戏：读来有来历，可作人设展开的支点"
    if kind == "pet":
        pt = ctx.get("pet_type")
        food_like = name in CREATIVE_BANKS["pet_food"]
        tip = "取食名，软糯好叫" if food_like else "叠词顺口，唤起来亲昵"
        if pt == "cat":
            tip = "猫感轻盈，轻唤即应" if not food_like else "取食名，猫主人都懂"
        if pt == "dog":
            tip = "憨实有力，喊得响" if not food_like else "取食名，憨态可掬"
        return tip
    if kind == "business":
        ind = ctx.get("industry")
        hint = INDUSTRY_HINT.get(ind, "吉祥稳重、朗朗上口")
        return f"{hint}，利于传播与记忆"
    return ""


class CreativeNamingService:
    """创意起名服务（同步、离线、确定性）。"""

    def generate(
        self,
        kind: str,
        keywords: str = "",
        style: Optional[str] = None,
        pet_type: Optional[str] = None,
        gender: Optional[str] = None,
        industry: Optional[str] = None,
        genre: Optional[str] = None,
        trait: Optional[str] = None,
        platform_type: Optional[str] = None,
        game_type: Optional[str] = None,
        count: int = 12,
    ) -> dict:
        if kind not in CREATIVE_KINDS:
            raise ValueError(f"kind 仅支持 {CREATIVE_KINDS}")

        toks = _tokenize(keywords)
        seed = _seed(kind, keywords, pet_type, gender, industry, genre, trait, platform_type, game_type)
        names = self._dispatch(
            kind, toks, pet_type, gender, industry, genre, trait,
            platform_type, game_type, count, seed,
        )

        # 类型/性格/平台/游戏类型的中文名（reason 文案用）
        genre_name = self._genre_name(genre) if genre else ""
        trait_name = self._trait_name(trait) if trait else ""
        platform_name = self._platform_name(platform_type) if platform_type else ""
        game_name = self._game_type_name(game_type) if game_type else ""

        return {
            "kind": kind,
            "total": len(names),
            "names": [
                {
                    "name": n,
                    "tag": KIND_NAMES[kind],
                    "reason": _reason(kind, n, {
                        "keywords": toks,
                        "pet_type": pet_type,
                        "industry": industry,
                        "genre_name": genre_name,
                        "trait_name": trait_name,
                        "platform_name": platform_name,
                        "game_name": game_name,
                    }),
                }
                for n in names
            ],
            # 未配置 LLM：如实标注「本地词库生成」，前端可据此展示
            "fallback_note": "当前为本地词库生成（未接入大模型）",
        }

    async def generate_llm(
        self,
        description: str,
        genre: Optional[str] = None,
        trait: Optional[str] = None,
        gender: Optional[str] = None,
        count: int = 12,
    ) -> dict:
        """
        自定义描述 → LLM 生成虚拟人物名（看广告解锁后调用）。

        LLM 未配置（settings.LLM_API_KEY 为空）或调用失败时，降级为本地词库生成，
        并以 source="local" 标注；成功时 source="llm"，附 provider/model。

        返回结构统一为：
            {"source", "total", "names": [{"name","tag","reason"}], "provider", "model", "fallback_note"}
        """
        genre_name = self._genre_name(genre)
        trait_name = self._trait_name(trait)

        # LLM 未配置：降级本地词库（尊重类型/性格；描述仅作随机种子）
        if not settings.LLM_API_KEY:
            return self._local_role_result(
                description, gender, genre, trait, count,
                "未配置大模型，已用本地词库生成；配置后可由用户看广告解锁 AI 生成",
            )

        llm = LLMService()
        prompt = self._build_role_llm_prompt(
            description, genre_name, trait_name, gender, count
        )
        try:
            response = await llm.chat(
                messages=[
                    {"role": "system", "content": _ROLE_LLM_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
                max_tokens=2048,
                json_mode=True,
            )
            pairs = self._parse_llm_names(response, count)
            if not pairs:
                raise LLMError("LLM 未产出有效名字")
        except LLMError as e:
            return self._local_role_result(
                description, gender, genre, trait, count,
                f"AI 生成失败（{e}），已降级为本地词库",
            )

        return {
            "source": "llm",
            "total": len(pairs),
            "names": [
                {"name": name, "tag": KIND_NAMES["role"], "reason": reason}
                for name, reason in pairs
            ],
            "provider": llm.provider,
            "model": llm.model,
            "fallback_note": None,
        }

    def _local_role_result(
        self, description, gender, genre, trait, count, note
    ) -> dict:
        """LLM 降级路径：本地词库生成 + 统一响应结构。"""
        local = self.generate(
            kind="role", keywords=description, gender=gender,
            genre=genre, trait=trait, count=count,
        )
        return {
            "source": "local",
            "total": local["total"],
            "names": local["names"],
            "provider": None,
            "model": None,
            "fallback_note": note,
        }

    @staticmethod
    def _build_role_llm_prompt(
        description, genre_name, trait_name, gender, count
    ) -> str:
        """构建虚拟人物起名的 LLM prompt（贴合设定 + 类型/性格约束）。"""
        genre_line = f"小说类型：{genre_name}" if genre_name else "小说类型：未指定，请根据设定自行把握"
        trait_line = f"性格特征：{trait_name}" if trait_name else "性格特征：未指定，请根据设定自行把握"
        gender_text = {"male": "男", "female": "女"}.get(gender, "未指定")
        return (
            "请为下面这个虚构角色起名。\n\n"
            f"【角色设定】\n{description.strip()}\n\n"
            f"【约束】\n- {genre_line}\n- {trait_line}\n- 角色性别：{gender_text}\n\n"
            f"请生成 {count} 个候选名字，要求：\n"
            "1. 以「姓 + 名」的中式人名为主（单姓），名字 1-2 字、整体 2-3 字；可少量附「字号 / 代号」式名字\n"
            "2. 名字贴合设定与类型底色，读来有画面、可作人设支点\n"
            "3. 不碰低俗、宗教、真实历史人物专名，不用生僻到打不出的字\n"
            "4. 每个名字给一句简短、不空泛的「为什么适合」理由\n\n"
            "按以下 JSON 格式输出（不要用代码块包裹，必须是合法 JSON）：\n"
            '{"names": [{"name": "沈云白", "reason": "仙侠底色、清冷气质，可作人设展开的支点"}]}'
        )

    @staticmethod
    def _parse_llm_names(response: dict, count: int) -> list[tuple[str, str]]:
        """把 LLM 返回的 JSON 解析成 [(name, reason)]，过滤空名/去重。"""
        raw = response.get("names") if isinstance(response, dict) else None
        if not isinstance(raw, list):
            return []
        out, seen = [], set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = re.sub(r"\s+", "", str(item.get("name") or ""))
            if not name or name in seen or len(name) > 6:
                continue
            reason = str(item.get("reason") or "").strip()
            seen.add(name)
            out.append((name, reason))
            if len(out) >= count:
                break
        return out

    def _dispatch(self, kind, toks, pet_type, gender, industry, genre, trait,
                  platform_type, game_type, count, seed) -> list[str]:
        if kind == "platform":
            return self._platform(toks, platform_type, count, seed)
        if kind == "game":
            return self._game(toks, game_type, count, seed)
        if kind == "role":
            return self._role(toks, gender, genre, trait, count, seed)
        if kind == "pet":
            return self._pet(pet_type, count, seed)
        if kind == "business":
            return self._business(industry, count, seed)
        return []

    @staticmethod
    def _find(options: list[dict], code: Optional[str]) -> Optional[dict]:
        """按 code 在词库列表里查（返回 None 表示未匹配）。"""
        if not code:
            return None
        return next((o for o in options if o["code"] == code), None)

    @classmethod
    def _genre_name(cls, code: Optional[str]) -> str:
        found = cls._find(NOVEL_GENRES, code)
        return found["name"] if found else ""

    @classmethod
    def _trait_name(cls, code: Optional[str]) -> str:
        found = cls._find(CHARACTER_TRAITS, code)
        return found["name"] if found else ""

    @classmethod
    def _platform_name(cls, code: Optional[str]) -> str:
        found = cls._find(PLATFORM_TYPES, code)
        return found["name"] if found else ""

    @classmethod
    def _game_type_name(cls, code: Optional[str]) -> str:
        found = cls._find(GAME_TYPES, code)
        return found["name"] if found else ""

    # ── 各 kind 组合逻辑 ──

    def _platform(self, toks, platform_type, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        bases, suffixes = self._platform_banks(platform_type)
        out = []
        # 关键词注入：仅 2-4 字的「名词感」输入作基底（放最前，让用户觉得被听见）
        for kw in [t for t in toks if 2 <= len(t) <= 4]:
            for suffix in _shuffled(suffixes, seed + 3, 3):
                out.append(f"{kw}{suffix}")
        out += _compose(bases, suffixes, count, seed)
        return self._dedup(out, count)

    @staticmethod
    def _platform_banks(platform_type):
        """按平台类型选词库（未指定回退通用 platform_bases/suffixes）。"""
        banks = CREATIVE_BANKS
        key_map = {
            "xiaohongshu": ("platform_bases", "platform_suffixes"),
            "zhihu": ("platform_bases_zhihu", "platform_suffixes_zhihu"),
            "douyin": ("platform_bases_douyin", "platform_suffixes_douyin"),
            "bilibili": ("platform_bases_bili", "platform_suffixes_bili"),
            "wechat": ("platform_bases_wechat", "platform_suffixes_wechat"),
        }
        bk, sk = key_map.get(platform_type, ("platform_bases", "platform_suffixes"))
        return banks[bk], banks[sk]

    def _game(self, toks, game_type, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        nuclei, tails = self._game_banks(game_type)
        out = []
        # 职业×游戏机制双轨：2 字「身份/职业」关键词 + 游戏机制语汇（如「温控」+「协议」）
        for kw in [t for t in toks if len(t) == 2]:
            for tail in _shuffled(banks["game_mech_tails"], seed + 3, 3):
                out.append(f"{kw}{tail}")
        # 游戏类型词库组合
        out += _compose(nuclei, tails, count, seed)
        return self._dedup(out, count)

    @staticmethod
    def _game_banks(game_type):
        """按游戏类型选词库（未指定回退 game_nuclei/tails）。"""
        banks = CREATIVE_BANKS
        key_map = {
            "fantasy": ("game_nuclei", "game_tails"),
            "scifi": ("game_scifi_nuclei", "game_scifi_tails"),
            "tactical": ("game_tactical_nuclei", "game_tactical_tails"),
            "casual": ("game_casual_nuclei", "game_casual_tails"),
        }
        nk, tk = key_map.get(game_type, ("game_nuclei", "game_tails"))
        return banks[nk], banks[tk]

    def _role(self, toks, gender, genre, trait, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        g = self._find(NOVEL_GENRES, genre)
        t = self._find(CHARACTER_TRAITS, trait)

        # 有类型/性格时，走「类型核 × 性格字」组合（性别字融入）
        if g or t:
            return self._role_typed(toks, g, t, gender, count, seed)

        # 无类型/性格：退回原「姓+名 + 代号」逻辑，按性别选名库
        surnames = _shuffled(banks["role_surnames"], seed)
        givens = self._role_givens(gender, seed + 1)
        out = []
        for i in range(min(count, len(surnames))):
            out.append(f"{surnames[i]}{givens[i % len(givens)]}")
        for kw in [t for t in toks if len(t) == 2]:
            out.append(kw)
        for code in _shuffled(banks["role_codes"], seed + 2):
            if len(out) >= count:
                break
            out.append(code)
        return self._dedup(out, count)

    @staticmethod
    def _role_givens(gender, seed):
        """按性别选名库（未指定回退中性 role_given）。"""
        banks = CREATIVE_BANKS
        if gender == "male":
            pool = banks["role_given_male"]
        elif gender == "female":
            pool = banks["role_given_female"]
        else:
            pool = banks["role_given"]
        return _shuffled(pool, seed)

    @staticmethod
    def _gender_chars(gender):
        """指定性别时的单字气质字（未指定返回空，不参与组合）。"""
        banks = CREATIVE_BANKS
        if gender == "male":
            return banks["role_male_chars"]
        if gender == "female":
            return banks["role_female_chars"]
        return []

    def _role_typed(self, toks, genre, trait, gender, count, seed) -> list[str]:
        """类型/性格驱动的虚拟人物起名：类型核字 × 性格气质字 → 姓+名 与 字号（含性别字）。"""
        banks = CREATIVE_BANKS
        surnames = _shuffled(banks["role_surnames"], seed)
        g_nuclei = (genre or {}).get("nuclei", [])
        t_atoms = (trait or {}).get("atoms", [])
        gender_chars = self._gender_chars(gender)
        out = []

        if g_nuclei and t_atoms:
            gn = _shuffled(g_nuclei, seed + 3)
            ta = _shuffled(t_atoms, seed + 4)
            n = min(len(surnames), len(gn), len(ta))
            # 性别字组合优先（最贴性别）：姓 + 类型核 + 性别字 / 姓 + 性格字 + 性别字（如「沈云衡」「沈白黛」）
            if gender_chars:
                gc = _shuffled(gender_chars, seed + 7)
                for i in range(n):
                    out.append(f"{surnames[i]}{gn[i]}{gc[i % len(gc)]}")
                    out.append(f"{surnames[i]}{ta[i]}{gc[i % len(gc)]}")
            # 类型核 × 性格字（正反字序各出一组，如「沈云白」）
            for i in range(n):
                out.append(f"{surnames[i]}{gn[i]}{ta[i]}")
                out.append(f"{surnames[i]}{ta[i]}{gn[i]}")
            # 字号：类型核 + 性格字（2 字，如「云白」）
            for gch in _shuffled(g_nuclei, seed + 5, 4):
                for tch in _shuffled(t_atoms, seed + 6, 4):
                    out.append(f"{gch}{tch}")
        elif g_nuclei:
            gn = _shuffled(g_nuclei, seed + 3)
            gn2 = _shuffled(g_nuclei, seed + 4)
            n = min(len(surnames), len(gn), len(gn2))
            # 性别字组合优先：姓 + 类型核 + 性别字（如「沈玄衡」）
            if gender_chars:
                gc = _shuffled(gender_chars, seed + 7)
                for i in range(n):
                    out.append(f"{surnames[i]}{gn[i]}{gc[i % len(gc)]}")
            # 仅类型：姓 + 类型核 + 类型核（双核错位，如「沈玄昊」）
            for i in range(n):
                if gn[i] != gn2[i]:
                    out.append(f"{surnames[i]}{gn[i]}{gn2[i]}")
            for gch in _shuffled(g_nuclei, seed + 5, 4):
                for gch2 in _shuffled(g_nuclei, seed + 6, 4):
                    if gch != gch2:
                        out.append(f"{gch}{gch2}")
        elif t_atoms:
            ta = _shuffled(t_atoms, seed + 3)
            ta2 = _shuffled(t_atoms, seed + 4)
            n = min(len(surnames), len(ta), len(ta2))
            # 性别字组合优先：姓 + 性格字 + 性别字（如「沈寒黛」）
            if gender_chars:
                gc = _shuffled(gender_chars, seed + 7)
                for i in range(n):
                    out.append(f"{surnames[i]}{ta[i]}{gc[i % len(gc)]}")
            # 仅性格：姓 + 性格字 + 性格字（如「沈寒素」）
            for i in range(n):
                if ta[i] != ta2[i]:
                    out.append(f"{surnames[i]}{ta[i]}{ta2[i]}")
            for tch in _shuffled(t_atoms, seed + 5, 4):
                for tch2 in _shuffled(t_atoms, seed + 6, 4):
                    if tch != tch2:
                        out.append(f"{tch}{tch2}")

        # 2 字关键词补充 + 代号兜底
        for kw in [t for t in toks if len(t) == 2]:
            out.append(kw)
        for code in _shuffled(banks["role_codes"], seed + 2):
            if len(out) >= count:
                break
            out.append(code)
        return self._dedup(out, count)

    def _pet(self, pet_type, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        pt = pet_type if pet_type in banks["pet_type_extra"] else "other"
        out = []
        # 种类专属词优先
        out += _shuffled(banks["pet_type_extra"][pt], seed, 3)
        out += _shuffled(banks["pet_food"], seed + 1)
        out += _shuffled(banks["pet_form"], seed + 2)
        out += _shuffled(banks["pet_bless"], seed + 3)
        return self._dedup(out, count)

    def _business(self, industry, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        ausp = _shuffled(banks["biz_ausp"], seed)
        suffixes = _shuffled(banks["biz_suffix"], seed + 1)
        out = []
        # 两字名（吉+吉）
        i = 0
        while len(out) < count and i + 1 < len(ausp):
            name = f"{ausp[i]}{ausp[i + 1]}"
            if name not in out:
                out.append(name)
            i += 2
        # 三字名（吉+吉+字号）补足到 count
        j = 0
        while len(out) < count and j + 1 < len(ausp):
            name = f"{ausp[j]}{ausp[j + 1]}{suffixes[j % len(suffixes)]}"
            if name not in out:
                out.append(name)
            j += 1
        return self._dedup(out, count)

    @staticmethod
    def _dedup(items, count):
        seen, out = set(), []
        for it in items:
            if it and it not in seen:
                seen.add(it)
                out.append(it)
            if len(out) >= count:
                break
        return out
