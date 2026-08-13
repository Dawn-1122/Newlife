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
        """匹配诗词典故"""
        poems = self.poetry_db.get_by_gender(gender)

        # 如果有喜用神，优先匹配推荐用字五行匹配的诗词
        matched = []
        for poem in poems:
            for char in poem["recommend_chars"]:
                char_info = self.char_db.get_char(char)
                if char_info:
                    if xiyong_wuxing and char_info["wuxing"] in xiyong_wuxing:
                        matched.append({**poem, "matched_char": char})
                    elif not xiyong_wuxing:
                        matched.append({**poem, "matched_char": char})

        return matched

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

        # 策略1：诗词优先——用诗词推荐字组名
        for pm in poetry_matches:
            char = pm["matched_char"]
            char_info = self.char_db.get_char(char)
            if not char_info:
                continue

            if name_length == 1:
                given_name = char
            else:
                # 双名：诗词字 + 另一个候选字
                # 从候选字中找一个搭配
                for other in candidate_chars:
                    if other["char"] == char:
                        continue
                    given_name = char + other["char"]
                    if given_name in seen_names:
                        continue
                    seen_names.add(given_name)
                    name_data = self._evaluate_name(
                        surname, given_name, [char_info, other],
                        pm, bazi_result
                    )
                    if name_data:
                        names.append(name_data)
                    break  # 每个诗词字只配一个

            if name_length == 1 and given_name not in seen_names:
                seen_names.add(given_name)
                name_data = self._evaluate_name(
                    surname, given_name, [char_info],
                    pm, bazi_result
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

        # 诗词加分
        poetry_score = 0
        if poetry_data:
            poetry_score = 15  # 有诗词出处加分

        # 综合评分
        # 音律30% + 五格25% + 八字25% + 诗词10% + 基础10%
        overall = (
            phonetics["score"] * 0.30
            + wuge.get("total_score", 60) * 0.25
            + bazi_score * 0.25
            + (70 + poetry_score) * 0.10
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
