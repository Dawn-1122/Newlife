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
from app.services.surname_fit import SurnameFit
from app.core.constants import NEGATIVE_CHARS, EMOTIONAL_CHARS, SAD_POETRY_TITLES, COMPOUND_SURNAMES, WUXING_LIST
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
        self.surname_fit = SurnameFit()

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
        selected_chars: Optional[list[str]] = None,
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
            selected_chars: 用户点选的候选字（两阶段流程：先选字再起名），
                            非空时名字用字限定为该集合

        Returns:
            {"bazi": {...}, "names": [...], "total": int, "fallback_note": str|None}
        """
        bazi_result, names = self._build_names(
            surname=surname, gender=gender, year=year, month=month, day=day,
            hour=hour, minute=minute, name_length=name_length,
            max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
            style=style, meanings=meanings, avoid_chars=avoid_chars,
            target_min=target_min, selected_chars=selected_chars,
        )

        fallback_note = None
        if (style or meanings) and len(names) < target_min and len(names) < max_results:
            _, fallback_names = self._build_names(
                surname=surname, gender=gender, year=year, month=month, day=day,
                hour=hour, minute=minute, name_length=name_length,
                max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
                style=None, meanings=None, avoid_chars=avoid_chars,
                target_min=target_min, selected_chars=selected_chars,
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
        selected_chars: Optional[list[str]] = None,
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

        # 2.5 用户点选字（两阶段流程）：限定候选字池为所选字
        if selected_chars:
            selected_set = set(selected_chars)
            selected_pool = [
                c for c in candidate_chars if c["char"] in selected_set
            ]
            # 若所选字不全在喜用神池中，从全字库补齐（保证用户所选字可用）
            if len(selected_pool) < len(selected_set):
                have = {c["char"] for c in selected_pool}
                for ch in selected_set - have:
                    info = self.char_db.get_char(ch)
                    if info and info["char"] not in blacklist:
                        selected_pool.append(info)
            candidate_chars = selected_pool

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
            selected_chars=selected_chars,
        )

        # 5. 韵味排序（韵味降序 → 喜用神 → 寓意 → 风格 tie-break）
        #    → 多样性重排 → 加权随机采样 → 剥离内部标记
        names = self._rank_by_yunwei(names, xiyong_wuxing, meanings, style)
        names = self._diversify(names, max_same_char=2)
        names = self._weighted_sample(names, max_results)
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

    @staticmethod
    def _weighted_sample(
        names: list[dict],
        k: int,
        temperature: float = 10.0,
    ) -> list[dict]:
        """
        加权随机采样（最终截取阶段，解决「换一批不变」）。

        从韵味分降序的候选里，取前若干高分做软加权不放回抽样，抽出 k 个：
        - 高分名字被抽中的概率更高（质量有保障）
        - 每次抽样结果不同（随机性）
        - 结果仍按韵味分降序返回（观感：高分在前）

        temperature 越大越均匀，越小越偏向最高分。
        """
        if not names:
            return names
        if len(names) <= k:
            sampled = list(names)
            random.shuffle(sampled)
            return sampled

        import math

        # 候选池取前 4k（或至少 60）个高分，保证质量下限
        pool_size = max(4 * k, 60)
        pool = list(names[:pool_size])
        weights = [math.exp(n["scores"]["yunwei"] / temperature) for n in pool]

        indices = list(range(len(pool)))
        total = sum(weights)
        picked: list[dict] = []
        for _ in range(k):
            if not indices or total <= 0:
                break
            r = random.random() * total
            cum = 0.0
            chosen = indices[-1]
            for idx in indices:
                cum += weights[idx]
                if r <= cum:
                    chosen = idx
                    break
            picked.append(pool[chosen])
            indices.remove(chosen)
            total -= weights[chosen]

        picked.sort(key=lambda n: -n["scores"]["yunwei"])
        return picked

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

    def _char_affinity(
        self,
        surname: str,
        char_info: dict,
        meanings: Optional[list[str]] = None,
    ) -> float:
        """
        单字亲和分（组合阶段软加权）：姓氏意象呼应 + 寓意偏好命中。

        用于候选字排序/随机加权，让不同姓氏、不同偏好在组合阶段就产生差异。
        分数只影响选字优先级，不进入韵味评分、不做硬过滤。
        """
        score = 0.0
        surname_info = self.surname_db.get_surname(surname)
        if surname_info:
            tags = [t for t in (surname_info.get("imagery") or []) if t]
            text = " ".join(filter(None, [
                char_info.get("meaning", ""),
                char_info.get("detail", ""),
                char_info.get("shuowen", ""),
            ]))
            for tag in tags:
                if tag and tag in text:
                    score += 3.0
                    break
        if meanings:
            score += self._meanings_match_score(
                char_info.get("meaning", ""), meanings
            ) * 2.0
        return score

    @staticmethod
    def _weighted_char_choice(chars: list[dict], top_n: int = 80) -> dict:
        """从候选字前 top_n（已按亲和分降序）里随机选一个，偏向姓氏/偏好匹配的字。"""
        pool = chars[:top_n]
        return random.choice(pool)

    def recommend_chars(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        limit_per_group: int = 8,
    ) -> dict:
        """
        两阶段流程第一步：根据用户信息推荐选字范围（按五行分组，喜用神优先）。

        Returns:
            {"bazi": {...}|None,
             "groups": [{"wuxing": str, "is_xiyong": bool,
                         "total": int, "chars": [字摘要...]}],
             "total": int}
        """
        # 1. 八字（如提供生辰）
        bazi_result = None
        xiyong_wuxing = None
        if year and month and day:
            bazi_result = self.bazi.generate_bazi(year, month, day, hour, minute, gender)
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 2. 会话黑名单
        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        # 3. 候选字（喜用神优先）
        candidate_chars = self._select_candidate_chars(
            xiyong_wuxing, gender, 2, blacklist, meanings
        )

        # 4. 姓氏结合预筛：剔除谐音歧义 / 本义冲突的字
        def fits_surname(c: dict) -> bool:
            taboo, _ = self.surname_fit.is_homophone_taboo(surname, c["char"])
            if taboo:
                return False
            conflict, _ = self.surname_fit.is_meaning_conflict(surname, c["char"])
            return not conflict

        candidate_chars = [c for c in candidate_chars if fits_surname(c)]

        # 5. 按五行分组，喜用神优先，每组取 top N
        xiyong_set = set(xiyong_wuxing or [])
        wuxing_order = list(xiyong_set) + [w for w in WUXING_LIST if w not in xiyong_set]
        groups = []
        for wx in wuxing_order:
            chars = [c for c in candidate_chars if c["wuxing"] == wx]
            if not chars:
                continue
            groups.append({
                "wuxing": wx,
                "is_xiyong": wx in xiyong_set,
                "total": len(chars),
                "chars": [self._char_brief(c) for c in chars[:limit_per_group]],
            })

        return {
            "bazi": bazi_result,
            "groups": groups,
            "total": sum(g["total"] for g in groups),
        }

    @staticmethod
    def _char_brief(c: dict) -> dict:
        """字摘要（选字推荐用，精简字段）。"""
        return {
            "char": c.get("char", ""),
            "pinyin": c.get("pinyin", ""),
            "wuxing": c.get("wuxing", ""),
            "kangxi_strokes": c.get("kangxi_strokes", 0),
            "gender": c.get("gender", "中"),
            "meaning": c.get("meaning", ""),
        }

    # ── 来源推荐（寓意优先 / 命格优先 两模式流程） ──

    def _source_wuxing_tendency(self, entry: dict) -> dict:
        """计算一条来源（诗词/字源）的五行倾向：基于推荐字的五行分布。"""
        dist: dict[str, int] = {}
        for ch in entry.get("recommend_chars", []):
            ci = self.char_db.get_char(ch)
            if not ci:
                continue
            wx = ci.get("wuxing", "")
            if wx:
                dist[wx] = dist.get(wx, 0) + 1
        if not dist:
            return {"wuxing_dist": {}, "tendency": [], "dominant": ""}
        max_cnt = max(dist.values())
        tendency = sorted(w for w, c in dist.items() if c == max_cnt)
        return {
            "wuxing_dist": dist,
            "tendency": tendency,
            "dominant": tendency[0],
        }

    def _available_source_entries(self, gender: str, blacklist: set) -> list[dict]:
        """收集所有可用来源（诗词 + 字源，排除哀伤、无可用推荐字）。"""
        entries: list[dict] = []
        entries.extend(self.poetry_db.get_by_gender(gender))
        entries.extend(self.source_db.get_by_gender(gender))
        blacklist = blacklist or set()
        seen: set = set()
        result: list[dict] = []
        for entry in entries:
            key = (entry["source"], entry["title"])
            if key in seen:
                continue
            seen.add(key)
            if self._is_sad_poem(entry):
                continue
            available = [
                c for c in entry.get("recommend_chars", [])
                if self.char_db.get_char(c) and c not in blacklist
            ]
            if not available:
                continue
            result.append(entry)
        return result

    def _find_source_by_id(self, source_id: str) -> Optional[dict]:
        """按 id 定位来源（诗词或字源）。"""
        for entry in self.poetry_db.get_all(include_sad=True):
            if entry.get("id") == source_id:
                return entry
        for entry in self.source_db.get_all(include_sad=True):
            if entry.get("id") == source_id:
                return entry
        return None

    @staticmethod
    def _bazi_explanation(bazi_result: Optional[dict]) -> Optional[dict]:
        """命格优先：把八字结果包装成人话解释 + 起名方向建议。"""
        if not bazi_result:
            return None
        xiyong = bazi_result.get("xiyong") or {}
        xi = xiyong.get("xi_wuxing", [])
        ji = xiyong.get("ji_wuxing", [])
        return {
            "day_master": xiyong.get("day_master", ""),
            "day_master_wuxing": xiyong.get("day_master_wuxing", ""),
            "strength_label": xiyong.get("strength_label", ""),
            "xi_wuxing": xi,
            "yong_wuxing": xiyong.get("yong_wuxing", ""),
            "ji_wuxing": ji,
            "suggestion": (
                f"命格{xiyong.get('strength_label', '')}，喜用神为"
                f"{'、'.join(xi) or '—'}，建议名字用{'、'.join(xi) or '喜用'}行字，"
                f"避开{'、'.join(ji) or '忌神'}行字。"
            ),
            "detail": xiyong.get("explanation", ""),
        }

    def recommend_sources(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        mode: str = "bazi_first",
        meanings: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        limit: int = 20,
    ) -> dict:
        """
        两模式流程第一步：推荐「来源」（诗句/古文），先不确定字。

        - mode="meaning_first"：按寓意匹配度排序（八字仅作忌神避让提示）
        - mode="bazi_first"：先给八字解释 + 方向，来源按喜用神倾向排序

        Returns:
            {"mode", "bazi", "bazi_explanation", "sources": [...], "total"}
        """
        bazi_result = None
        xiyong_wuxing: list[str] = []
        ji_wuxing: list[str] = []
        if year and month and day:
            bazi_result = self.bazi.generate_bazi(year, month, day, hour, minute, gender)
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]

        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        entries = self._available_source_entries(gender, blacklist)

        xi_set = set(xiyong_wuxing)
        ji_set = set(ji_wuxing)

        decorated = []
        for entry in entries:
            tendency = self._source_wuxing_tendency(entry)
            blob = " ".join(entry.get("imagery", []) or []) + " "
            blob += (entry.get("scene", "") or "") + " "
            blob += (entry.get("text", "") or "")
            meaning_score = (
                self._meanings_match_score(blob, meanings) if meanings else 0
            )
            dom = tendency["dominant"]
            if dom and dom in xi_set:
                bazi_flag = "xiyong"
            elif dom and dom in ji_set:
                bazi_flag = "ji"
            else:
                bazi_flag = "neutral"
            decorated.append((entry, tendency, meaning_score, bazi_flag))

        def sort_key(item):
            _e, _t, m_score, flag = item
            flag_rank = {"xiyong": 0, "neutral": 1, "ji": 2}
            if mode == "bazi_first":
                return (flag_rank[flag], -m_score)
            # 寓意优先：寓意分降序，忌神倾向在同分内排后
            return (-m_score, flag_rank[flag])

        decorated.sort(key=sort_key)

        sources = []
        for entry, tendency, m_score, flag in decorated:
            sources.append(
                self._source_brief(entry, tendency, flag, m_score, meanings)
            )
            if len(sources) >= limit:
                break

        return {
            "mode": mode,
            "bazi": bazi_result,
            "bazi_explanation": self._bazi_explanation(bazi_result),
            "sources": sources,
            "total": len(sources),
        }

    def _source_brief(
        self,
        entry: dict,
        tendency: dict,
        flag: str,
        m_score: int,
        meanings: Optional[list[str]],
    ) -> dict:
        """来源摘要（来源推荐用）。"""
        reason = ""
        if flag == "xiyong":
            reason = f"意境偏{tendency['dominant']}，契合命格喜用神"
        elif flag == "ji":
            reason = f"意境偏{tendency['dominant']}，与命格忌神相冲，建议避开"
        if m_score > 0 and meanings:
            names = [MEANING_OPTIONS[m].get("name", m) for m in meanings]
            reason = (reason + "；" if reason else "") + "契合寓意「" + "、".join(names) + "」"
        if not reason:
            reason = "意境中正，可供参考"
        return {
            "id": entry.get("id", ""),
            "source": entry.get("source", ""),
            "source_class": entry.get("source_class", entry.get("source", "")),
            "title": entry.get("title", ""),
            "author": entry.get("author", "佚名"),
            "dynasty": entry.get("dynasty", ""),
            "text": entry.get("text", ""),
            "citation": entry.get("citation", ""),
            "imagery": entry.get("imagery", []),
            "scene": entry.get("scene", ""),
            "recommend_chars": entry.get("recommend_chars", []),
            "wuxing_tendency": tendency["dominant"],
            "wuxing_dist": tendency["wuxing_dist"],
            "bazi_flag": flag,
            "match_reason": reason,
        }

    def source_chars(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        source_ids: Optional[list[str]] = None,
        limit_per_source: int = 8,
    ) -> dict:
        """
        两模式流程第二步：用户选定来源后，在该来源内按八字喜用神推荐字。

        Returns:
            {"bazi", "sources": [{"id", "source", "title", "text",
                                  "wuxing_tendency", "chars": [...]}], "total"}
        """
        bazi_result = None
        xiyong_wuxing: list[str] = []
        ji_wuxing: list[str] = []
        if year and month and day:
            bazi_result = self.bazi.generate_bazi(year, month, day, hour, minute, gender)
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]

        blacklist = set(NEGATIVE_CHARS)
        xi_set = set(xiyong_wuxing)
        ji_set = set(ji_wuxing)

        result_sources = []
        for sid in (source_ids or []):
            entry = self._find_source_by_id(sid)
            if not entry:
                continue
            valid_chars = self._get_valid_poem_chars(
                entry, gender, xiyong_wuxing, blacklist, None
            )

            def rank(c):
                wx = c["wuxing"]
                if xi_set and wx in xi_set:
                    return 0
                if ji_set and wx in ji_set:
                    return 2
                return 1

            valid_chars.sort(key=rank)
            tendency = self._source_wuxing_tendency(entry)
            result_sources.append({
                "id": entry.get("id", ""),
                "source": entry.get("source", ""),
                "title": entry.get("title", ""),
                "text": entry.get("text", ""),
                "wuxing_tendency": tendency["dominant"],
                "chars": [
                    self._source_char_brief(c, xi_set, ji_set)
                    for c in valid_chars[:limit_per_source]
                ],
            })

        return {
            "bazi": bazi_result,
            "sources": result_sources,
            "total": sum(len(s["chars"]) for s in result_sources),
        }

    @staticmethod
    def _source_char_brief(c: dict, xi_set: set, ji_set: set) -> dict:
        """来源内选字摘要（含喜用神/忌神标记）。"""
        wx = c.get("wuxing", "")
        if wx in xi_set:
            flag = "xiyong"
        elif wx in ji_set:
            flag = "ji"
        else:
            flag = "neutral"
        return {
            "char": c.get("char", ""),
            "pinyin": c.get("pinyin", ""),
            "wuxing": wx,
            "kangxi_strokes": c.get("kangxi_strokes", 0),
            "gender": c.get("gender", "中"),
            "meaning": c.get("meaning", ""),
            "bazi_flag": flag,
        }

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
            # 寓意命中：诗词 imagery/scene/text 命中寓意关键词 → 提升为 tier A（软加权优先引入）
            if meanings:
                blob = blob_of(entry)
                for m in meanings:
                    opt = MEANING_OPTIONS.get(m)
                    if opt and any(kw in blob for kw in opt.get("keywords", [])):
                        return "A"
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
        selected_chars: Optional[list[str]] = None,
    ) -> list[dict]:
        """组合生成名字（预算式 + tier 标记）。"""
        names = []
        seen_names = set()
        blacklist = blacklist or set()
        selected_set = set(selected_chars) if selected_chars else None

        xiyong_wuxing = None
        if bazi_result:
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        candidate_chars = [
            c for c in candidate_chars if c["char"] not in blacklist
        ]

        # 候选字按「姓氏意象呼应 + 偏好命中」亲和分降序（稳定排序，喜用神优先顺序作 tie-break）
        candidate_chars = sorted(
            candidate_chars,
            key=lambda c: -self._char_affinity(surname, c, meanings),
        )

        def compose_from_entry(entry: dict, tier: str) -> None:
            """从单条出处的推荐字里生成同源名字。"""
            valid_chars = self._get_valid_poem_chars(
                entry, gender, xiyong_wuxing, blacklist, meanings
            )
            # 姓氏参与：同源字按姓氏亲和分排序，让不同姓氏优先取不同字
            valid_chars = sorted(
                valid_chars,
                key=lambda c: -self._char_affinity(surname, c, meanings),
            )
            # 两阶段流程：用户点选字后，出处组合也限定为所选字
            if selected_set:
                valid_chars = [c for c in valid_chars if c["char"] in selected_set]

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
                        # 姓氏结合：三连同调（全平/全仄）提前跳过
                        if self.surname_fit.tri_tone_conflict(
                            surname, [c1["char"], c2["char"]]
                        ):
                            continue
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

        # 策略1：同源组名，按 tier 预算式（A → B → C），tier 内随机 shuffle + 总量封顶
        tier_groups: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
        for entry, tier in provenance_matches:
            tier_groups.setdefault(tier, []).append(entry)

        # tier 内随机打乱诗词顺序，让每次调用的同源组合不同（解决「换一批不变」）
        for tier in ("A", "B", "C"):
            random.shuffle(tier_groups.get(tier, []))

        has_preference_tiers = bool(tier_groups.get("A") or tier_groups.get("B"))
        cap = max(pool_size * 4, 120)

        for tier in ("A", "B", "C"):
            if len(names) >= cap:
                break
            for entry in tier_groups.get(tier, []):
                compose_from_entry(entry, tier)
                # 有偏好时，命中偏好的 A/B 组合达到 target_min 即截断（C 仍兜底）
                if has_preference_tiers and tier != "C" and len(names) >= target_min:
                    break
                if len(names) >= cap:
                    break

        # 策略2：随机组合（始终参与，补充多样性 + 姓氏/偏好引导）
        if candidate_chars:
            budget = max(pool_size, 40)
            max_attempts = budget * 10
            attempts = 0
            random_count = 0
            while random_count < budget and attempts < max_attempts:
                attempts += 1
                if name_length == 1:
                    char_info = self._weighted_char_choice(candidate_chars)
                    given_name = char_info["char"]
                else:
                    c1 = self._weighted_char_choice(candidate_chars)
                    c2 = self._weighted_char_choice(candidate_chars)
                    while c2["char"] == c1["char"]:
                        c2 = self._weighted_char_choice(candidate_chars)
                    # 姓氏结合：三连同调（全平/全仄）跳过
                    if self.surname_fit.tri_tone_conflict(
                        surname, [c1["char"], c2["char"]]
                    ):
                        continue
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
                    random_count += 1

        return names

    def _pass_gate(
        self,
        surname: str,
        given_name: str,
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
        - 姓氏谐音歧义（杜子腾/吴德/杨伟 类，安全底线）
        - 姓氏本义冲突（朱+红 重复、白+云 贬义）
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
        # 姓氏结合：谐音歧义 / 本义冲突（硬排除，安全底线）
        taboo, _ = self.surname_fit.is_homophone_taboo(surname, given_name)
        if taboo:
            return False
        conflict, _ = self.surname_fit.is_meaning_conflict(surname, given_name)
        if conflict:
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
        if not self._pass_gate(surname, given_name, phonetics, wuge, bazi_result, chars_info):
            return None

        # 情绪字软门槛（分级放开）：含负面情绪字的名字须「有出处 + 名内有正向/中性字」
        emotional_hit = [c["char"] for c in chars_info if c["char"] in EMOTIONAL_CHARS]
        has_emotional = bool(emotional_hit)
        if has_emotional and (not entry or len(emotional_hit) == len(chars_info)):
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
            "emotional": has_emotional,
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
