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
                ]
            }
        """
        # 1. 八字分析（如提供生辰）
        bazi_result = None
        xiyong_wuxing = None
        if use_bazi and year and month and day:
            bazi_result = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 2. 候选字筛选
        candidate_chars = self._select_candidate_chars(
            xiyong_wuxing, gender, name_length
        )

        # 3. 诗词匹配（优先用诗词出处的字）
        poetry_matches = []
        if use_poetry:
            poetry_matches = self._match_poetry(xiyong_wuxing, gender)

        # 4. 生成名字组合
        names = self._compose_names(
            surname, candidate_chars, poetry_matches,
            gender, name_length, bazi_result
        )

        # 5. 排序并截取
        names.sort(key=lambda n: n["scores"]["overall"], reverse=True)
        names = names[:max_results]

        return {
            "bazi": bazi_result,
            "names": names,
            "total": len(names),
        }

    def _select_candidate_chars(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        name_length: int = 2,
    ) -> list[dict]:
        """筛选候选字"""
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

        return chars

    def _match_poetry(
        self, xiyong_wuxing: list[str] = None, gender: str = "male"
    ) -> list[dict]:
        """
        匹配诗词典故

        返回去重后的诗词列表（每首只返回一次），保留所有有可用推荐字的诗。
        喜用神匹配不再硬性过滤，而是交由评分排序（_evaluate_name 的 bazi_score 已占权重），
        这样同源组名能覆盖足够多的诗词，含义连贯的名字不会被八字偏好误伤。
        """
        poems = self.poetry_db.get_by_gender(gender)

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

            # 只要有可用字（字库中存在）就纳入
            available = [c for c in poem["recommend_chars"] if self.char_db.get_char(c)]
            if not available:
                continue

            matched.append(poem)

        return matched

    @staticmethod
    def _is_sad_poem(poem: dict) -> bool:
        """判断诗词是否为哀伤类（标题命中黑名单）"""
        title = poem.get("title", "")
        source_title = f'{poem.get("source", "")}·{title}'
        for sad in SAD_POETRY_TITLES:
            if sad in title or sad in source_title:
                return True
        return False

    def _get_valid_poem_chars(
        self, poem: dict, gender: str, xiyong_wuxing: list[str] = None
    ) -> list[dict]:
        """从一首诗词的推荐字里筛选出可用字（字库存在 + 符合性别 + 非负面字），喜用神匹配的字排前"""
        valid = []
        for char in poem["recommend_chars"]:
            ci = self.char_db.get_char(char)
            if not ci:
                continue
            # 过滤负面字黑名单
            if ci["char"] in NEGATIVE_CHARS:
                continue
            if gender == "male" and ci["gender"] not in ("男", "中"):
                continue
            if gender == "female" and ci["gender"] not in ("女", "中"):
                continue
            valid.append(ci)
        # 喜用神匹配的字排前面，这样同源组名时优先用补益八字的字
        if xiyong_wuxing:
            valid.sort(key=lambda c: 0 if c["wuxing"] in xiyong_wuxing else 1)
        return valid

    def _compose_names(
        self,
        surname: str,
        candidate_chars: list[dict],
        poetry_matches: list[dict],
        gender: str,
        name_length: int,
        bazi_result: dict = None,
    ) -> list[dict]:
        """组合生成名字"""
        names = []
        seen_names = set()

        # 喜用神（用于同源组名时优先取补益八字的字）
        xiyong_wuxing = None
        if bazi_result:
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 过滤负面字黑名单（策略2随机组合的候选字来源）
        candidate_chars = [
            c for c in candidate_chars if c["char"] not in NEGATIVE_CHARS
        ]

        # 策略1：同源组名——名字的两个字出自同一首诗词，含义完整连贯
        for poem in poetry_matches:
            valid_chars = self._get_valid_poem_chars(poem, gender, xiyong_wuxing)

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
                        names.append(name_data)
            else:
                # 双名：从同一首诗词里取两个字
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
                            names.append(name_data)

        # 策略2：随机组合候选字（补充数量）
        if len(names) < 15:
            for _ in range(50):
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
                    names.append(name_data)

                if len(names) >= 30:
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
