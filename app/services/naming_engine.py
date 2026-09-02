"""
起名核心引擎

整合八字引擎 + 字库 + 诗词库 + 字源库 + 音律评分 + 五格数理 + 韵味评分，
生成完整的名字候选列表。

评分架构（重构后）：
- 硬过滤层（安全底线）：负面字黑名单 + 用户避讳字 + luck=凶 ∪ blacklist.json
- 第一层门槛（只排除、不打分）：音律严重拗口 / 五格人格总格双凶 / 八字全忌神
- 第二层排序：韵味（出处/意象/余味/名内呼应/姓氏协调）——决定谁排前面
    - 韵味同分 tie-break：喜用神命中数 → 寓意命中数 → 风格命中数
    - _diversify 多样性重排 → 截取 max_results

scores.overall 语义变更 = 韵味分（主排序依据）；scores.phonetics/wuge/bazi 退化为展示值。
"""

import random
from typing import Optional
from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.source_database import SourceDatabase
from app.services.surname_database import SurnameDatabase
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.services.yunwei_scorer import YunWeiScorer
from app.services.llm_service import LLMService
from app.services.meaning_cache import MeaningCache
from app.core.constants import NEGATIVE_CHARS, SAD_POETRY_TITLES, COMPOUND_SURNAMES
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
        self.source_db = SourceDatabase()
        self.surname_db = SurnameDatabase()
        self.yunwei = YunWeiScorer(
            surname_db=self.surname_db,
            source_db=self.source_db,
            poetry_db=self.poetry_db,
        )
        self.phonetics = PhoneticsScorer()
        self.wuge = WugeScorer()
        self.bazi = BaziEngine()
        self.llm = LLMService()
        self.cache = MeaningCache()

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
            style: 风格偏好 code（选池偏置 + 末级 tie-break，不再强加权压过韵味）
            meanings: 期望寓意 code 列表（选字硬前置 + 二级 tie-break）
            avoid_chars: 避讳字列表，硬剔除
            industry: 行业 code，P0 仅透传不参与打分
            target_min: 同源组名目标最小数量

        Returns:
            {"bazi": {...}, "names": [...], "total": int, "fallback_note": str|None}
        """
        bazi_result, names = self._build_names(
            surname=surname, gender=gender, year=year, month=month, day=day,
            hour=hour, minute=minute, name_length=name_length,
            max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
            style=style, meanings=meanings, avoid_chars=avoid_chars,
            target_min=target_min,
        )

        fallback_note = None
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
                fallback_note = "已尽量贴合偏好，其余按韵味评分补充"

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
        """核心起名流程（八字 → 候选字 → 出处匹配 → 组名 → 门槛/韵味 → 排序/多样性/截取）。"""
        # 1. 八字分析（如提供生辰）
        bazi_result = None
        xiyong_wuxing = None
        if use_bazi and year and month and day:
            bazi_result = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 0. 会话黑名单 = 负面字 + 用户避讳字（硬过滤）
        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        # 2. 候选字筛选
        candidate_chars = self._select_candidate_chars(
            xiyong_wuxing, gender, name_length, blacklist, meanings
        )

        # 3. 出处匹配（诗词 + 字源，统一出处抽象）
        provenance_matches = self._match_provenance(
            xiyong_wuxing, gender, style, meanings, blacklist,
            use_poetry=use_poetry,
        )

        # 4. 生成名字组合
        names = self._compose_names(
            surname, candidate_chars, provenance_matches,
            gender, name_length, bazi_result, blacklist, meanings,
            target_min=target_min, pool_size=max_results,
        )

        # 5. 韵味排序（韵味降序 → 喜用神 → 寓意 → 风格 tie-break）
        #    → 多样性重排 → 截取 → 剥离内部标记
        names = self._rank_by_yunwei(names, xiyong_wuxing, meanings, style)
        names = self._diversify(names, max_same_char=2)
        names = names[:max_results]
        for n in names:
            n.pop("_tier", None)

        return bazi_result, names

    @staticmethod
    def _diversify(names: list[dict], max_same_char: int = 2) -> list[dict]:
        """
        多样性重排：限制同一个字（尤其名字首字）在结果中反复出现。

        贪心策略——按韵味分降序遍历（调用方已排序），维护每个字已出现次数：
        - 首字出现 >= max_same_char 次则暂缓放入 deferred；
        - 否则纳入，并累加该名字所有字的出现次数。
        被跳过的 deferred 仍按韵味分降序补到末尾。不删除任何名字。
        """
        if not names or max_same_char < 1:
            return names

        counts: dict[str, int] = {}
        kept: list[dict] = []
        deferred: list[dict] = []

        for name in names:
            given_name = name.get("given_name", "")
            first_char = given_name[0] if given_name else ""

            if first_char and counts.get(first_char, 0) >= max_same_char:
                deferred.append(name)
                continue

            kept.append(name)
            for ch in given_name:
                counts[ch] = counts.get(ch, 0) + 1

        deferred.sort(key=lambda n: n["scores"]["yunwei"], reverse=True)
        return kept + deferred

    def _rank_by_yunwei(
        self,
        names: list[dict],
        xiyong_wuxing: Optional[list[str]],
        meanings: Optional[list[str]],
        style: Optional[str],
    ) -> list[dict]:
        """韵味降序排序，同分依次按喜用神命中数 → 寓意命中数 → 风格命中数 tie-break。"""

        def xiyong_hits(n: dict) -> int:
            if not xiyong_wuxing:
                return 0
            return sum(
                1 for c in n.get("chars_info", [])
                if c.get("wuxing") in xiyong_wuxing
            )

        def meaning_hits(n: dict) -> int:
            if not meanings:
                return 0
            text = "".join(
                (c.get("meaning") or "") for c in n.get("chars_info", [])
            )
            return NamingEngine._meanings_match_score(text, meanings)

        def style_hits(n: dict) -> int:
            if not style or style not in STYLE_OPTIONS:
                return 0
            entry = n.get("poetry") or {}
            blob = " ".join(entry.get("imagery", []) or []) + " "
            blob += (entry.get("scene", "") or "") + " "
            blob += (entry.get("text", "") or "")
            return NamingEngine._meanings_match_score(
                blob, STYLE_OPTIONS[style].get("imagery_keywords", [])
            )

        names.sort(
            key=lambda n: (
                -n["scores"]["yunwei"],
                -xiyong_hits(n),
                -meaning_hits(n),
                -style_hits(n),
            )
        )
        return names

    def _select_candidate_chars(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        name_length: int = 2,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
    ) -> list[dict]:
        """筛选候选字（黑名单硬过滤 + 寓意关键词硬前置）。"""
        blacklist = blacklist or set()
        if xiyong_wuxing:
            chars = []
            for wx in xiyong_wuxing:
                chars.extend(self.char_db.get_by_wuxing(wx, gender))
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
            chars = self.char_db.filter(gender=gender)

        chars = [c for c in chars if c["char"] not in blacklist]

        if meanings:
            chars.sort(
                key=lambda c: 0
                if self._meanings_match_score(c.get("meaning", ""), meanings) > 0
                else 1
            )

        return chars

    def _match_provenance(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        blacklist: set = None,
        use_poetry: bool = True,
    ) -> list[tuple]:
        """
        统一出处匹配：合并诗词库 + 字源库条目，返回 [(entry, tier), ...]。

        去重后保留所有有可用推荐字的条目，tier ∈ {A, B, C} 仅用于候选池预算式引入顺序，
        不再决定最终排序（最终排序由韵味分决定）。
        """
        entries = []
        if use_poetry:
            entries.extend(self.poetry_db.get_by_gender(gender))
        entries.extend(self.source_db.get_by_gender(gender))

        blacklist = blacklist or set()
        matched = []
        seen = set()
        for entry in entries:
            key = (entry["source"], entry["title"])
            if key in seen:
                continue
            seen.add(key)

            if NamingEngine._is_sad_poem(entry):
                continue

            available = [
                c for c in entry["recommend_chars"]
                if self.char_db.get_char(c) and c not in blacklist
            ]
            if not available:
                continue

            matched.append(entry)

        return self._rank_poems(matched, style, meanings)

    @staticmethod
    def _rank_poems(
        entries: list[dict],
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
    ) -> list[tuple]:
        """
        分层打分 + tier 标记（仅影响选池引入顺序，不决定最终排序）。

        - Tier A：source 或 source_class 命中该风格的 source_preference
        - Tier B：非 A 但 imagery_keywords 命中
        - Tier C：其余（兜底）
        """
        if not style and not meanings:
            return [(e, "C") for e in entries]

        tier_rank = {"A": 0, "B": 1, "C": 2}

        def blob_of(entry: dict) -> str:
            imagery = " ".join(entry.get("imagery", []) or [])
            scene = entry.get("scene", "") or ""
            text = entry.get("text", "") or ""
            return f"{imagery} {scene} {text}"

        def tier_of(entry: dict) -> str:
            if style and style in STYLE_OPTIONS:
                opt = STYLE_OPTIONS[style]
                prefs = opt.get("source_preference", [])
                # 字源 source_class 归入「经史子集」，与诗词 source 统一命中
                if (entry.get("source", "") in prefs
                        or entry.get("source_class", "") in prefs):
                    return "A"
                blob = blob_of(entry)
                if any(kw in blob for kw in opt.get("imagery_keywords", [])):
                    return "B"
            return "C"

        def score_of(entry: dict) -> int:
            total = 0
            blob = blob_of(entry)
            if style and style in STYLE_OPTIONS:
                opt = STYLE_OPTIONS[style]
                prefs = opt.get("source_preference", [])
                if (entry.get("source", "") in prefs
                        or entry.get("source_class", "") in prefs):
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

        decorated = [(tier_of(e), score_of(e), e) for e in entries]
        decorated.sort(key=lambda x: (tier_rank[x[0]], -x[1]))
        return [(e, t) for t, _score, e in decorated]

    @staticmethod
    def _is_sad_poem(poem: dict) -> bool:
        """判断出处是否为哀伤类（标题命中黑名单；字源条目 emotion 已由读层过滤）。"""
        title = poem.get("title", "")
        source_title = f'{poem.get("source", "")}·{title}'
        for sad in SAD_POETRY_TITLES:
            if sad in title or sad in source_title:
                return True
        return False

    @staticmethod
    def _meanings_match_score(text: str, meanings: Optional[list[str]]) -> int:
        """计算文本命中寓意关键词的次数（用于候选字/出处软排序与 tie-break）。"""
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
        """从一条出处条目（诗词/字源）的推荐字里筛出可用字（字库存在 + 性别 + 非黑名单）。"""
        blacklist = set(NEGATIVE_CHARS) if blacklist is None else set(blacklist)
        valid = []
        for char in poem["recommend_chars"]:
            ci = self.char_db.get_char(char)
            if not ci:
                continue
            if ci["char"] in blacklist:
                continue
            if gender == "male" and ci["gender"] not in ("男", "中"):
                continue
            if gender == "female" and ci["gender"] not in ("女", "中"):
                continue
            valid.append(ci)

        def sort_key(c: dict) -> tuple:
            meaning_hit = 0 if (
                meanings
                and NamingEngine._meanings_match_score(c.get("meaning", ""), meanings) > 0
            ) else 1
            xiyong_rank = 0 if (xiyong_wuxing and c["wuxing"] in xiyong_wuxing) else 1
            return (meaning_hit, xiyong_rank)

        valid.sort(key=sort_key)
        return valid

    def _find_entry_for_char(self, char: str) -> Optional[dict]:
        """按字查找一条出处条目（优先诗词，其次字源）。"""
        poems = self.poetry_db.get_by_char(char)
        if poems:
            return poems[0]
        sources = self.source_db.get_by_char(char)
        if sources:
            return sources[0]
        return None

    def _compose_names(
        self,
        surname: str,
        candidate_chars: list[dict],
        provenance_matches: list[tuple],
        gender: str,
        name_length: int,
        bazi_result: dict = None,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
        target_min: int = TARGET_MIN,
        pool_size: int = 30,
    ) -> list[dict]:
        """组合生成名字（预算式 + tier 标记）。"""
        names = []
        seen_names = set()
        blacklist = blacklist or set()

        xiyong_wuxing = None
        if bazi_result:
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        candidate_chars = [
            c for c in candidate_chars if c["char"] not in blacklist
        ]

        def compose_from_entry(entry: dict, tier: str) -> None:
            """从单条出处的推荐字里生成同源名字。"""
            valid_chars = self._get_valid_poem_chars(
                entry, gender, xiyong_wuxing, blacklist, meanings
            )

            if name_length == 1:
                for ci in valid_chars:
                    given_name = ci["char"]
                    if given_name in seen_names:
                        continue
                    seen_names.add(given_name)
                    name_data = self._evaluate_name(
                        surname, given_name, [ci], entry, bazi_result
                    )
                    if name_data:
                        name_data["_tier"] = tier
                        names.append(name_data)
            else:
                for i in range(len(valid_chars)):
                    for j in range(i + 1, len(valid_chars)):
                        c1, c2 = valid_chars[i], valid_chars[j]
                        given_name = c1["char"] + c2["char"]
                        if given_name in seen_names:
                            continue
                        seen_names.add(given_name)
                        name_data = self._evaluate_name(
                            surname, given_name, [c1, c2], entry, bazi_result
                        )
                        if name_data:
                            name_data["_tier"] = tier
                            names.append(name_data)

        # 策略1：同源组名，按 tier 预算式生成（A → B → C）
        tier_groups: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
        for entry, tier in provenance_matches:
            tier_groups.setdefault(tier, []).append(entry)

        has_preference_tiers = bool(tier_groups.get("A") or tier_groups.get("B"))

        for tier in ("A", "B", "C"):
            if has_preference_tiers and len(names) >= target_min:
                break
            for entry in tier_groups.get(tier, []):
                compose_from_entry(entry, tier)
                if has_preference_tiers and len(names) >= target_min:
                    break

        # 策略2：随机组合候选字，兜底到 pool_size
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

                entry = self._find_entry_for_char(char_info["char"])

                chars_info = []
                for c in given_name:
                    ci = self.char_db.get_char(c)
                    if ci:
                        chars_info.append(ci)

                name_data = self._evaluate_name(
                    surname, given_name, chars_info, entry, bazi_result
                )
                if name_data:
                    name_data["_tier"] = "R"
                    names.append(name_data)

                if len(names) >= pool_size:
                    break

        return names

    def _pass_gate(
        self,
        phonetics: dict,
        wuge: dict,
        bazi_result: Optional[dict],
        chars_info: list[dict],
    ) -> bool:
        """
        第一层门槛：只排除、不打分。

        - 音律严重拗口（全平/全仄 或 score<55）
        - 五格人格、总格双凶
        - 八字全忌神（名字所有字五行都在忌神）
        """
        if self.phonetics.is_cacophonous(phonetics):
            return False
        if self.wuge.is_bad(wuge):
            return False
        if bazi_result:
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]
            name_wuxing = [c["wuxing"] for c in chars_info]
            if name_wuxing and BaziEngine.is_ji_wuxing_conflict(name_wuxing, ji_wuxing):
                return False
        return True

    def _evaluate_name(
        self,
        surname: str,
        given_name: str,
        chars_info: list[dict],
        entry: dict = None,
        bazi_result: dict = None,
    ) -> Optional[dict]:
        """评估单个名字：过门槛 → 韵味评分 → 组装返回。"""
        full_name = surname + given_name

        phonetics = self.phonetics.analyze(full_name)

        try:
            wuge = self.wuge.calculate(surname, given_name)
        except Exception:
            wuge = {"total_score": 60, "description": "数理计算异常"}

        # 门槛：任一不通过 → 丢弃（不进候选）
        if not self._pass_gate(phonetics, wuge, bazi_result, chars_info):
            return None

        # 八字匹配展示值（不再参与主排序）
        bazi_score = 70
        if bazi_result and chars_info:
            xiyong = bazi_result["xiyong"]["xi_wuxing"]
            matched = sum(1 for ci in chars_info if ci["wuxing"] in xiyong)
            bazi_score = 60 + int(matched / len(chars_info) * 40)

        # 韵味评分（含 S 姓氏协调）
        yunwei_detail = self.yunwei.score(surname, chars_info, entry)
        yunwei_total = yunwei_detail["total"]

        meaning = self._generate_meaning(chars_info, entry)

        return {
            "full_name": full_name,
            "given_name": given_name,
            "chars_info": [
                {
                    "char": ci["char"],
                    "pinyin": ci.get("pinyin", ""),
                    "wuxing": ci.get("wuxing", ""),
                    "kangxi_strokes": ci.get("kangxi_strokes", 0),
                    "meaning": ci.get("meaning", ""),
                    "shuowen": ci.get("shuowen", ""),
                    "detail": ci.get("detail", ""),
                    "radical": ci.get("radical", ""),
                    "imagery": ci.get("imagery", []),
                    "level": ci.get("level", "一"),
                }
                for ci in chars_info
            ],
            "poetry": {
                "source": entry["source"],
                "title": entry["title"],
                "author": entry.get("author", "佚名"),
                "dynasty": entry.get("dynasty", ""),
                "text": entry.get("text", ""),
                "citation": entry.get("citation", ""),
                "source_class": entry.get("source_class", entry.get("source", "")),
                "imagery": entry.get("imagery", []),
                "scene": entry.get("scene", ""),
            } if entry else None,
            "phonetics": phonetics,
            "wuge": wuge,
            "scores": {
                "phonetics": phonetics["score"],
                "wuge": wuge.get("total_score", 60),
                "bazi": bazi_score,
                "overall": yunwei_total,
                "yunwei": yunwei_total,
                "yunwei_detail": yunwei_detail,
            },
            "meaning": meaning,
        }

    @staticmethod
    def _generate_meaning(chars_info: list[dict], entry: dict = None) -> str:
        """生成寓意简述（模板兜底，LLM 懒加载见 generate_meaning_detail）。"""
        meanings = [ci.get("meaning", "") for ci in chars_info if ci.get("meaning")]

        if entry:
            source = f"「{entry['source']}·{entry['title']}」"
            text = entry.get("text", "")
            char_meanings = "，".join(meanings)
            return f"出自{source}「{text}」。{char_meanings}。"
        return "，".join(meanings) + "。"

    # ── LLM 寓意懒加载（详情页） ──

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str]:
        """拆分姓与名（兼容复姓）。"""
        for cs in COMPOUND_SURNAMES:
            if full_name.startswith(cs):
                return cs, full_name[len(cs):]
        return full_name[0], full_name[1:]

    def _lookup_chars(self, given_name: str) -> list[dict]:
        """按名字用字查字库，缺失字兜底。"""
        chars_info = []
        for c in given_name:
            info = self.char_db.get_char(c)
            if info:
                chars_info.append(info)
            else:
                chars_info.append({
                    "char": c,
                    "pinyin": "",
                    "wuxing": "未知",
                    "kangxi_strokes": 0,
                    "meaning": "字库中暂无此字信息",
                    "shuowen": "",
                    "detail": "",
                    "radical": "",
                    "imagery": [],
                    "level": "扩展",
                })
        return chars_info

    def _find_best_entry(self, given_name: str, chars_info: list[dict]) -> Optional[dict]:
        """为名字查找最佳出处条目（优先同源，其次单字出处）。"""
        name_chars = [c["char"] for c in chars_info]
        # 同源优先
        for ch in name_chars:
            for entry in self.source_db.get_by_char(ch):
                rec = entry["recommend_chars"]
                if name_chars and all(x in rec for x in name_chars):
                    return entry
            for entry in self.poetry_db.get_by_char(ch):
                rec = entry["recommend_chars"]
                if name_chars and all(x in rec for x in name_chars):
                    return entry
        # 单字出处兜底
        for ch in name_chars:
            src = self.source_db.get_by_char(ch)
            if src:
                return src[0]
            poem = self.poetry_db.get_by_char(ch)
            if poem:
                return poem[0]
        return None

    @staticmethod
    def _wuxing_note(chars_info: list[dict]) -> str:
        """模板兜底：名字五行说明。"""
        if not chars_info:
            return ""
        parts = [f"{c['char']}属{c.get('wuxing', '未知')}" for c in chars_info]
        return "、".join(parts) + "，五行搭配"

    async def generate_meaning_detail(
        self,
        full_name: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
    ) -> dict:
        """
        详情页懒加载：为单个名字生成「多层余味」寓意。

        LLM 成功 → 多层 layers + meaning_source="llm"；失败 → 模板兜底 + meaning_source="template"。
        结果写入缓存（key = full_name + gender + 生辰签名 + citation）。
        """
        surname, given_name = self._split_name(full_name)
        chars_info = self._lookup_chars(given_name)
        entry = self._find_best_entry(given_name, chars_info)

        bazi_data = None
        bazi_signature = None
        if year and month and day:
            bazi_data = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            bazi_signature = f"{year}-{month}-{day}-{hour}-{minute}"

        citation = (entry or {}).get("citation", "")
        key = self.cache.build_key(full_name, gender, bazi_signature, citation)
        cached = self.cache.get(key)
        if cached:
            return cached

        result = await self.llm.generate_meaning(
            full_name, chars_info, entry, bazi_data, gender
        )

        if result.get("error") or not result.get("layers"):
            fallback = {
                "full_name": full_name,
                "given_name": given_name,
                "surname": surname,
                "citation": citation,
                "layers": self._fallback_layers(chars_info, entry),
                "meaning": self._generate_meaning(chars_info, entry),
                "poetry_note": (
                    f"出自{citation}" if citation else "名字用字自有其文化意蕴"
                ),
                "wuxing_note": self._wuxing_note(chars_info),
                "overall_note": self._generate_meaning(chars_info, entry),
                "meaning_source": "template",
            }
            self.cache.set(key, fallback)
            return fallback

        result["full_name"] = full_name
        result["given_name"] = given_name
        result["surname"] = surname
        result["citation"] = citation
        result["meaning_source"] = "llm"
        self.cache.set(key, result)
        return result

    @staticmethod
    def _fallback_layers(chars_info: list[dict], entry: Optional[dict]) -> list[dict]:
        """模板兜底的三层余味结构。"""
        literal = "、".join(
            (c.get("meaning") or "未收录") for c in chars_info
        )
        layers = [{"level": "字面", "text": f"名字用字取义：{literal}"}]
        if entry:
            layers.append({
                "level": "出处",
                "text": f"出自{entry.get('citation', '')}「{entry.get('text', '')}」",
            })
        layers.append({
            "level": "余味",
            "text": "名字自有其深意，可细细品味其文化意蕴",
        })
        return layers
