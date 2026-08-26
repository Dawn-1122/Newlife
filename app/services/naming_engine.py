"""
起名核心引擎

整合八字引擎 + 字库 + 诗词库 + 音律评分 + 五格数理，
生成完整的名字候选列表。

每个候选名字包含：
- 名字（姓+名）
- 八字匹配分析
- 诗词出处（如有）
- 音律评分
- 五格数理评分
- 综合评分
- 寓意简述
"""

import random
from typing import Optional
from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.core.config import settings
from app.core.constants import NEGATIVE_CHARS, SAD_POETRY_TITLES
from app.core.naming_options import (
    STYLE_OPTIONS,
    MEANING_OPTIONS,
    STYLE_TIER_A_WEIGHT,
    MEANING_KEYWORD_WEIGHT,
    IMAGERY_WEIGHT,
    TARGET_MIN,
)


class NamingEngine:
    """起名核心引擎"""

    def __init__(self):
        self.char_db = CharDatabase()
        self.poetry_db = PoetryDatabase()
        self.phonetics = PhoneticsScorer()
        self.wuge = WugeScorer()
        self.bazi = BaziEngine()

    def generate_names(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        name_length: int = 2,
        max_results: int = 30,
        use_bazi: bool = True,
        use_poetry: bool = True,
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        industry: Optional[str] = None,
        target_min: int = TARGET_MIN,
    ) -> dict:
        """
        生成名字候选列表

        Args:
            surname: 姓氏
            gender: male / female
            year/month/day/hour/minute: 出生时间（可选，不提供则不做八字分析）
            name_length: 名字字数（1或2，不含姓）
            max_results: 最大返回数量
            use_bazi: 是否使用八字分析
            use_poetry: 是否使用诗词典故
            style: 风格偏好 code（classic|modern|grand|fresh），强加权（分层打分）
            meanings: 期望寓意 code 列表（最多3个），强加权（寓意命中硬前置）
            avoid_chars: 避讳字列表，硬剔除（并入会话黑名单）
            industry: 行业 code，P0 仅透传不参与打分
            target_min: 强加权同源组名的目标最小数量（不足则降级软排序兜底）

        Returns:
            {
                "bazi": {...},  # 八字分析结果（如使用）
                "names": [      # 名字候选列表
                    {
                        "full_name": "张伟",
                        "given_name": "伟",
                        "chars_info": [{...}, ...],
                        "poetry": {...} | None,  # 诗词出处
                        "phonetics": {...},      # 音律分析
                        "wuge": {...},           # 五格数理
                        "scores": {
                            "phonetics": 85,
                            "wuge": 80,
                            "bazi": 90,
                            "overall": 85
                        },
                        "meaning": "...",        # 寓意简述
                    },
                    ...
                ],
                "fallback_note": str | None,  # 强加权候选不足时降级的提示标记
            }
        """
        bazi_result, names = self._build_names(
            surname=surname, gender=gender, year=year, month=month, day=day,
            hour=hour, minute=minute, name_length=name_length,
            max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
            style=style, meanings=meanings, avoid_chars=avoid_chars,
            target_min=target_min,
        )

        fallback_note = None
        # 强加权兜底：候选不足 target_min 且未满足 max_results 时，降级为软排序
        # （不传 style/meanings 的默认行为），避免偏好把候选集挤到过小。
        if (style or meanings) and len(names) < target_min and len(names) < max_results:
            _, fallback_names = self._build_names(
                surname=surname, gender=gender, year=year, month=month, day=day,
                hour=hour, minute=minute, name_length=name_length,
                max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
                style=None, meanings=None, avoid_chars=avoid_chars,
                target_min=target_min,
            )
            if len(fallback_names) > len(names):
                names = fallback_names
                fallback_note = "已尽量贴合偏好，其余按综合评分补充"

        return {
            "bazi": bazi_result,
            "names": names,
            "total": len(names),
            "fallback_note": fallback_note,
        }

    def _build_names(
        self,
        surname: str,
        gender: str,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        name_length: int,
        max_results: int,
        use_bazi: bool,
        use_poetry: bool,
        style: Optional[str],
        meanings: Optional[list[str]],
        avoid_chars: Optional[list[str]],
        target_min: int,
    ) -> tuple:
        """
        核心起名流程（八字 → 候选字 → 诗词匹配 → 组名 → 排序/多样性/截取）。

        供 `generate_names` 与强加权降级兜底复用，返回 (bazi_result, names)。
        """
        # 1. 八字分析（如提供生辰）
        bazi_result = None
        xiyong_wuxing = None
        if use_bazi and year and month and day:
            bazi_result = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 0. 会话黑名单 = 负面字 + 用户避讳字（硬过滤，候选与组合阶段都剔除）
        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        # 2. 候选字筛选
        candidate_chars = self._select_candidate_chars(
            xiyong_wuxing, gender, name_length, blacklist, meanings
        )

        # 3. 诗词匹配（优先用诗词出处的字）
        poetry_matches = []
        if use_poetry:
            poetry_matches = self._match_poetry(
                xiyong_wuxing, gender, style, meanings, blacklist
            )

        # 4. 生成名字组合
        names = self._compose_names(
            surname, candidate_chars, poetry_matches,
            gender, name_length, bazi_result, blacklist, meanings,
            target_min=target_min, pool_size=max_results,
        )

        # 5. 排序（tier 强加权：A > B > C > R；组内寓意命中优先，再按综合分）
        #    → 多样性重排 → 截取 → 剥离内部标记
        tier_rank = {"A": 0, "B": 1, "C": 2, "R": 3}

        def name_meaning_score(name: dict) -> int:
            """统计名字各字义命中寓意关键词的次数（0 表示未命中）"""
            if not meanings:
                return 0
            text = "".join(
                (c.get("meaning") or "") for c in name.get("chars_info", [])
            )
            return NamingEngine._meanings_match_score(text, meanings)

        names.sort(
            key=lambda n: (
                tier_rank.get(n.get("_tier"), 3),
                -name_meaning_score(n),
                -n["scores"]["overall"],
            )
        )
        names = self._diversify(names, max_same_char=2)
        names = names[:max_results]
        for n in names:
            n.pop("_tier", None)

        return bazi_result, names

    @staticmethod
    def _diversify(names: list[dict], max_same_char: int = 2) -> list[dict]:
        """
        多样性重排：限制同一个字（尤其名字首字）在结果中反复出现。

        采用贪心策略——按 overall 降序遍历（调用方已排序），维护每个字已出现的次数：
        - 若某名字的首字已出现 >= max_same_char 次，则暂时跳过并放入 deferred；
        - 否则纳入结果，并累加该名字所有字的出现次数。
        被跳过的 deferred 仍按 overall 降序补到末尾。

        注意：本方法只改变排序顺序，不删除任何名字。
        """
        if not names or max_same_char < 1:
            return names

        counts: dict[str, int] = {}
        kept: list[dict] = []
        deferred: list[dict] = []

        for name in names:
            given_name = name.get("given_name", "")
            first_char = given_name[0] if given_name else ""

            # 首字已出现达到上限则暂缓，避免「海存/海深/海涯」同字扎堆
            if first_char and counts.get(first_char, 0) >= max_same_char:
                deferred.append(name)
                continue

            kept.append(name)
            # 累加名字所有字的出现次数（含首字）
            for ch in given_name:
                counts[ch] = counts.get(ch, 0) + 1

        # 暂缓的名字按 overall 降序补到末尾
        deferred.sort(key=lambda n: n["scores"]["overall"], reverse=True)
        return kept + deferred

    def _select_candidate_chars(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        name_length: int = 2,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
    ) -> list[dict]:
        """筛选候选字（并做黑名单硬过滤 + 寓意关键词排序）"""
        blacklist = blacklist or set()
        if xiyong_wuxing:
            # 优先选喜用神五行
            chars = []
            for wx in xiyong_wuxing:
                chars.extend(self.char_db.get_by_wuxing(wx, gender))
            # 如果不够，补充其他五行
            if len(chars) < 20:
                all_chars = self.char_db.get_all()
                for c in all_chars:
                    if c not in chars:
                        if gender == "male":
                            if c["gender"] in ("男", "中"):
                                chars.append(c)
                        elif gender == "female":
                            if c["gender"] in ("女", "中"):
                                chars.append(c)
                        else:
                            chars.append(c)
        else:
            # 无八字分析，按性别选字
            chars = self.char_db.filter(gender=gender)

        # 硬剔除负面字与避讳字
        chars = [c for c in chars if c["char"] not in blacklist]

        # 寓意关键词命中硬前置：命中寓意的字排前（稳定排序，保留组内喜用神优先次序）
        if meanings:
            chars.sort(
                key=lambda c: 0
                if self._meanings_match_score(c.get("meaning", ""), meanings) > 0
                else 1
            )

        return chars

    def _match_poetry(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        blacklist: set = None,
    ) -> list[dict]:
        """
        匹配诗词典故

        返回去重后的诗词列表（每首只返回一次），保留所有有可用推荐字的诗，
        每首诗带 tier 标记：[(poem, tier), ...]，tier ∈ {A, B, C}。
        喜用神匹配不再硬性过滤，而是交由评分排序（_evaluate_name 的 bazi_score 已占权重），
        这样同源组名能覆盖足够多的诗词，含义连贯的名字不会被八字偏好误伤。
        风格/寓意为分层打分（强加权），不硬删，保证候选量充足。
        """
        poems = self.poetry_db.get_by_gender(gender)
        blacklist = blacklist or set()

        matched = []
        seen = set()
        for poem in poems:
            key = (poem["source"], poem["title"])
            if key in seen:
                continue
            seen.add(key)

            # 过滤哀伤类诗词（避免「国破山河在」等负面意境出处）
            if NamingEngine._is_sad_poem(poem):
                continue

            # 只要有可用字（字库中存在且非黑名单）就纳入
            available = [
                c for c in poem["recommend_chars"]
                if self.char_db.get_char(c) and c not in blacklist
            ]
            if not available:
                continue

            matched.append(poem)

        # 风格/寓意排序加权
        return self._rank_poems(matched, style, meanings)

    @staticmethod
    def _rank_poems(
        poems: list[dict],
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
    ) -> list[tuple]:
        """
        分层打分 + tier 标记。

        - Tier A：source 命中该风格的 source_preference（权重 STYLE_TIER_A_WEIGHT）
        - Tier B：非 A 但 imagery_keywords 命中（权重 IMAGERY_WEIGHT）
        - Tier C：其余（兜底，不硬删）
        - 寓意 keyword 命中（权重 MEANING_KEYWORD_WEIGHT）参与组内排序

        返回 [(poem, tier), ...]，先按 tier（A→B→C），组内按得分降序。
        不污染 poetry.json 原数据（tier 仅以元组形式存在于局部返回值中）。
        """
        if not style and not meanings:
            return [(p, "C") for p in poems]

        tier_rank = {"A": 0, "B": 1, "C": 2}

        def blob_of(poem: dict) -> str:
            imagery = " ".join(poem.get("imagery", []) or [])
            scene = poem.get("scene", "") or ""
            text = poem.get("text", "") or ""
            return f"{imagery} {scene} {text}"

        def tier_of(poem: dict) -> str:
            if style and style in STYLE_OPTIONS:
                opt = STYLE_OPTIONS[style]
                if poem.get("source", "") in opt.get("source_preference", []):
                    return "A"
                blob = blob_of(poem)
                if any(kw in blob for kw in opt.get("imagery_keywords", [])):
                    return "B"
            return "C"

        def score_of(poem: dict) -> int:
            total = 0
            blob = blob_of(poem)
            if style and style in STYLE_OPTIONS:
                opt = STYLE_OPTIONS[style]
                if poem.get("source", "") in opt.get("source_preference", []):
                    total += STYLE_TIER_A_WEIGHT
                for kw in opt.get("imagery_keywords", []):
                    if kw in blob:
                        total += IMAGERY_WEIGHT
            if meanings:
                for m in meanings:
                    opt = MEANING_OPTIONS.get(m)
                    if not opt:
                        continue
                    for kw in opt.get("keywords", []):
                        if kw in blob:
                            total += MEANING_KEYWORD_WEIGHT
            return total

        decorated = [(tier_of(p), score_of(p), p) for p in poems]
        decorated.sort(key=lambda x: (tier_rank[x[0]], -x[1]))
        return [(p, t) for t, _score, p in decorated]

    @staticmethod
    def _is_sad_poem(poem: dict) -> bool:
        """判断诗词是否为哀伤类（标题命中黑名单）"""
        title = poem.get("title", "")
        source_title = f'{poem.get("source", "")}·{title}'
        for sad in SAD_POETRY_TITLES:
            if sad in title or sad in source_title:
                return True
        return False

    @staticmethod
    def _meanings_match_score(text: str, meanings: Optional[list[str]]) -> int:
        """计算文本命中寓意关键词的次数（用于候选字/诗词软排序）"""
        if not meanings or not text:
            return 0
        score = 0
        for m in meanings:
            opt = MEANING_OPTIONS.get(m)
            if not opt:
                continue
            for kw in opt.get("keywords", []):
                if kw in text:
                    score += 1
        return score

    def _get_valid_poem_chars(
        self,
        poem: dict,
        gender: str,
        xiyong_wuxing: list[str] = None,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
    ) -> list[dict]:
        """从一首诗词的推荐字里筛选出可用字（字库存在 + 符合性别 + 非黑名单），喜用神/寓意匹配的字排前"""
        # 缺省时默认使用负面字黑名单，保持向后兼容（外部直接调用不传 blacklist 也能过滤）
        blacklist = set(NEGATIVE_CHARS) if blacklist is None else set(blacklist)
        valid = []
        for char in poem["recommend_chars"]:
            ci = self.char_db.get_char(char)
            if not ci:
                continue
            # 过滤负面字/避讳字黑名单
            if ci["char"] in blacklist:
                continue
            if gender == "male" and ci["gender"] not in ("男", "中"):
                continue
            if gender == "female" and ci["gender"] not in ("女", "中"):
                continue
            valid.append(ci)
        # 寓意命中硬前置 > 喜用神命中 > 其余（寓意对得上的字在组合时优先被取到）
        def sort_key(c: dict) -> tuple:
            meaning_hit = 0 if (
                meanings
                and NamingEngine._meanings_match_score(c.get("meaning", ""), meanings) > 0
            ) else 1
            xiyong_rank = 0 if (xiyong_wuxing and c["wuxing"] in xiyong_wuxing) else 1
            return (meaning_hit, xiyong_rank)

        valid.sort(key=sort_key)
        return valid

    def _compose_names(
        self,
        surname: str,
        candidate_chars: list[dict],
        poetry_matches: list[tuple],
        gender: str,
        name_length: int,
        bazi_result: dict = None,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
        target_min: int = TARGET_MIN,
        pool_size: int = 30,
    ) -> list[dict]:
        """
        组合生成名字（预算式 + tier 标记）。

        策略1（同源组名）按 tier 顺序生成：先用 Tier A 诗词出名字，不足 target_min
        再引入 Tier B，仍不足再引入 Tier C；最后策略2 随机组合兜底补足到 pool_size。
        每个名字附带内部 `_tier` 标记（A/B/C/R），供上层排序时强加权、返回前剥离。
        """
        names = []
        seen_names = set()
        blacklist = blacklist or set()

        # 喜用神（用于同源组名时优先取补益八字的字）
        xiyong_wuxing = None
        if bazi_result:
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 过滤负面字/避讳字黑名单（策略2随机组合的候选字来源）
        candidate_chars = [
            c for c in candidate_chars if c["char"] not in blacklist
        ]

        def compose_from_poem(poem: dict, tier: str) -> None:
            """从单首诗词的推荐字里生成同源名字（双名取同诗两字，单名取一字）"""
            valid_chars = self._get_valid_poem_chars(
                poem, gender, xiyong_wuxing, blacklist, meanings
            )

            if name_length == 1:
                for ci in valid_chars:
                    given_name = ci["char"]
                    if given_name in seen_names:
                        continue
                    seen_names.add(given_name)
                    name_data = self._evaluate_name(
                        surname, given_name, [ci], poem, bazi_result
                    )
                    if name_data:
                        name_data["_tier"] = tier
                        names.append(name_data)
            else:
                # 双名：从同一首诗词里取两个字，含义完整连贯
                for i in range(len(valid_chars)):
                    for j in range(i + 1, len(valid_chars)):
                        c1, c2 = valid_chars[i], valid_chars[j]
                        given_name = c1["char"] + c2["char"]
                        if given_name in seen_names:
                            continue
                        seen_names.add(given_name)
                        name_data = self._evaluate_name(
                            surname, given_name, [c1, c2], poem, bazi_result
                        )
                        if name_data:
                            name_data["_tier"] = tier
                            names.append(name_data)

        # 策略1：同源组名，按 tier 预算式生成（A → B → C）
        tier_groups: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
        for poem, tier in poetry_matches:
            tier_groups.setdefault(tier, []).append(poem)

        # 存在偏好 tier（A/B）时才启用预算截断；无偏好时遍历全部诗词保留出处覆盖
        has_preference_tiers = bool(tier_groups.get("A") or tier_groups.get("B"))

        for tier in ("A", "B", "C"):
            if has_preference_tiers and len(names) >= target_min:
                break
            for poem in tier_groups.get(tier, []):
                compose_from_poem(poem, tier)
                if has_preference_tiers and len(names) >= target_min:
                    break

        # 策略2：随机组合候选字（补充数量 + 提供换一批随机性），兜底到 pool_size
        if len(names) < pool_size and candidate_chars:
            max_attempts = max(pool_size * 6, 100)
            for _ in range(max_attempts):
                if name_length == 1:
                    char_info = random.choice(candidate_chars)
                    given_name = char_info["char"]
                else:
                    c1 = random.choice(candidate_chars)
                    c2 = random.choice(candidate_chars)
                    while c2["char"] == c1["char"]:
                        c2 = random.choice(candidate_chars)
                    given_name = c1["char"] + c2["char"]
                    char_info = c1

                if given_name in seen_names:
                    continue
                seen_names.add(given_name)

                # 查找是否有对应诗词
                poem = self.poetry_db.get_by_char(char_info["char"])
                poem_data = poem[0] if poem else None

                chars_info = []
                for c in given_name:
                    ci = self.char_db.get_char(c)
                    if ci:
                        chars_info.append(ci)

                name_data = self._evaluate_name(
                    surname, given_name, chars_info,
                    poem_data, bazi_result
                )
                if name_data:
                    name_data["_tier"] = "R"
                    names.append(name_data)

                if len(names) >= pool_size:
                    break

        return names

    def _evaluate_name(
        self,
        surname: str,
        given_name: str,
        chars_info: list[dict],
        poetry_data: dict = None,
        bazi_result: dict = None,
    ) -> Optional[dict]:
        """评估单个名字"""
        full_name = surname + given_name

        # 音律评分
        phonetics = self.phonetics.analyze(full_name)

        # 五格数理
        try:
            wuge = self.wuge.calculate(surname, given_name)
        except Exception:
            wuge = {"total_score": 60, "description": "数理计算异常"}

        # 八字匹配评分
        bazi_score = 70  # 默认
        if bazi_result and chars_info:
            xiyong = bazi_result["xiyong"]["xi_wuxing"]
            matched = 0
            for ci in chars_info:
                if ci["wuxing"] in xiyong:
                    matched += 1
            bazi_score = 60 + int(matched / len(chars_info) * 40)

        # 诗词加分（同源 > 单字出处 > 无）
        poetry_score = 0
        if poetry_data:
            rec_chars = poetry_data.get("recommend_chars", [])
            name_chars = [ci["char"] for ci in chars_info]
            if name_chars and all(c in rec_chars for c in name_chars):
                poetry_score = 25  # 同源：名字的字都出自同一首诗词
            else:
                poetry_score = 10  # 单字出处

        # 综合评分
        # 音律25% + 五格20% + 八字25% + 诗词20% + 基础10%
        poetry_component = poetry_score / 25 * 100  # 同源100 / 单字40 / 无0
        overall = (
            phonetics["score"] * 0.25
            + wuge.get("total_score", 60) * 0.20
            + bazi_score * 0.25
            + poetry_component * 0.20
            + 70 * 0.10
        )
        overall = round(overall)

        # 寓意简述
        meaning = self._generate_meaning(chars_info, poetry_data)

        return {
            "full_name": full_name,
            "given_name": given_name,
            "chars_info": [
                {
                    "char": ci["char"],
                    "pinyin": ci["pinyin"],
                    "wuxing": ci["wuxing"],
                    "kangxi_strokes": ci["kangxi_strokes"],
                    "meaning": ci["meaning"],
                    "shuowen": ci.get("shuowen", ""),
                    "detail": ci.get("detail", ""),
                }
                for ci in chars_info
            ],
            "poetry": {
                "source": poetry_data["source"],
                "title": poetry_data["title"],
                "author": poetry_data["author"],
                "dynasty": poetry_data["dynasty"],
                "text": poetry_data["text"],
            } if poetry_data else None,
            "phonetics": phonetics,
            "wuge": wuge,
            "scores": {
                "phonetics": phonetics["score"],
                "wuge": wuge.get("total_score", 60),
                "bazi": bazi_score,
                "overall": overall,
            },
            "meaning": meaning,
        }

    @staticmethod
    def _generate_meaning(chars_info: list[dict], poetry_data: dict = None) -> str:
        """生成寓意简述"""
        meanings = [ci["meaning"] for ci in chars_info if ci.get("meaning")]

        if poetry_data:
            source = f"「{poetry_data['source']}·{poetry_data['title']}」"
            text = poetry_data["text"]
            char_meanings = "，".join(meanings)
            return f"出自{source}「{text}」。{char_meanings}。"
        else:
            return "，".join(meanings) + "。"
