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

from app.core.naming_options import INDUSTRY_WUXING

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


def _reason(kind, name, ctx) -> str:
    """给出一条简短、不空泛的「为什么适合」文案。"""
    kw = ctx.get("keywords")
    if kind == "platform":
        base = f"贴合「{kw[0]}」的定位，" if kw else ""
        return f"{base}意象克制、留有生活肌理，好记也耐读"
    if kind == "game":
        return "意象与机制语汇交织，辨识度高、社区二创友好"
    if kind == "role":
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
        count: int = 12,
    ) -> dict:
        if kind not in CREATIVE_KINDS:
            raise ValueError(f"kind 仅支持 {CREATIVE_KINDS}")

        toks = _tokenize(keywords)
        seed = _seed(kind, keywords, pet_type, gender, industry)
        names = self._dispatch(kind, toks, pet_type, gender, industry, count, seed)

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
                    }),
                }
                for n in names
            ],
            # 未配置 LLM：如实标注「本地词库生成」，前端可据此展示
            "fallback_note": "当前为本地词库生成（未接入大模型）",
        }

    def _dispatch(self, kind, toks, pet_type, gender, industry, count, seed) -> list[str]:
        if kind == "platform":
            return self._platform(toks, count, seed)
        if kind == "game":
            return self._game(toks, count, seed)
        if kind == "role":
            return self._role(toks, gender, count, seed)
        if kind == "pet":
            return self._pet(pet_type, count, seed)
        if kind == "business":
            return self._business(industry, count, seed)
        return []

    # ── 各 kind 组合逻辑 ──

    def _platform(self, toks, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        out = []
        # 关键词注入：仅 2-4 字的「名词感」输入作基底（放最前，让用户觉得被听见）
        for kw in [t for t in toks if 2 <= len(t) <= 4]:
            for suffix in _shuffled(banks["platform_suffixes"], seed + 3, 3):
                out.append(f"{kw}{suffix}")
        out += _compose(banks["platform_bases"], banks["platform_suffixes"], count, seed)
        return self._dedup(out, count)

    def _game(self, toks, count, seed) -> list[str]:
        # 游戏昵称的关键词多为「身份/品类」长语义描述，缺 LLM 时无法安全组词，
        # 故不作字面注入，只取意象核×状态尾的词库组合，保证质量。
        banks = CREATIVE_BANKS
        out = _compose(banks["game_nuclei"], banks["game_tails"], count, seed)
        return self._dedup(out, count)

    def _role(self, toks, gender, count, seed) -> list[str]:
        banks = CREATIVE_BANKS
        surnames = _shuffled(banks["role_surnames"], seed)
        givens = _shuffled(banks["role_given"], seed + 1)
        out = []
        # 姓 + 名（中式，主输出）
        for i in range(min(count, len(surnames))):
            out.append(f"{surnames[i]}{givens[i % len(givens)]}")
        # 2 字关键词可作代号式补充（如「守阈」），长设定仅作 reason 语境
        for kw in [t for t in toks if len(t) == 2]:
            out.append(kw)
        # 代号补充到够数
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
