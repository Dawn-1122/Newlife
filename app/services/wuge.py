"""
五格数理评分模块

五格剖象法：根据姓名的康熙笔画计算天格、人格、地格、外格、总格，
再对照81数理吉凶表评分。

注意：五格数理为传统文化参考，非科学定论。
"""

from app.services.char_database import CharDatabase


class WugeScorer:
    """五格数理评分器"""

    # 81数理吉凶表（1-81，简化版）
    # 吉: 1,3,5,6,7,8,11,13,15,16,17,18,21,23,24,25,29,31,32,33,35,37,39,41,45,47,48,52,57,61,63,65,67,68,81
    # 凶: 2,4,9,10,12,14,19,20,22,26,27,28,30,34,36,38,40,42,43,44,46,49,50,51,53,54,56,58,59,60,62,64,66,69,70,71,72,73,74,76,77,78,79,80
    LUCKY_NUMBERS = {
        1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18,
        21, 23, 24, 25, 29, 31, 32, 33, 35, 37, 39,
        41, 45, 47, 48, 52, 57, 61, 63, 65, 67, 68, 81
    }

    # 大吉之数（额外加分）
    GREAT_LUCKY = {1, 3, 5, 6, 8, 11, 13, 15, 16, 21, 23, 24, 25, 31, 32, 33, 35, 37, 39, 41}

    @classmethod
    def calculate(cls, surname: str, given_name: str) -> dict:
        """
        计算五格数理

        Args:
            surname: 姓氏（单姓或复姓）
            given_name: 名字（一个或两个字）

        Returns:
            {
                "tian_ge": {"value": 8, "luck": "吉", "meaning": "..."},
                "ren_ge": {"value": 15, "luck": "吉", "meaning": "..."},
                "di_ge": {"value": 8, "luck": "吉", "meaning": "..."},
                "wai_ge": {"value": 8, "luck": "吉", "meaning": "..."},
                "zong_ge": {"value": 15, "luck": "吉", "meaning": "..."},
                "total_score": 85,
                "description": "五格数理整体评价"
            }
        """
        char_db = CharDatabase()

        # 获取所有字的康熙笔画
        surname_chars = list(surname)
        given_chars = list(given_name)
        all_chars = surname_chars + given_chars

        strokes = []
        for c in all_chars:
            char_info = char_db.get_char(c)
            if char_info:
                strokes.append(char_info["kangxi_strokes"])
            else:
                # 非字库中的字，用简体笔画估算（实际应查康熙字典）
                strokes.append(len(c))

        # 单姓 vs 复姓
        is_compound_surname = len(surname_chars) > 1
        # 单名 vs 双名
        is_single_name = len(given_chars) == 1

        if not is_compound_surname:
            # 单姓
            surname_stroke = strokes[0]
            if is_single_name:
                # 单姓单名：姓 + 名
                name_stroke1 = strokes[1]
                # 天格 = 姓 + 1
                tian = surname_stroke + 1
                # 人格 = 姓 + 名
                ren = surname_stroke + name_stroke1
                # 地格 = 名 + 1
                di = name_stroke1 + 1
                # 外格 = 2（固定）
                wai = 2
                # 总格 = 姓 + 名
                zong = surname_stroke + name_stroke1
            else:
                # 单姓双名：姓 + 名1 + 名2
                name_stroke1 = strokes[1]
                name_stroke2 = strokes[2]
                tian = surname_stroke + 1
                ren = surname_stroke + name_stroke1
                di = name_stroke1 + name_stroke2
                wai = name_stroke2 + 1
                zong = surname_stroke + name_stroke1 + name_stroke2
        else:
            # 复姓
            surname_stroke1 = strokes[0]
            surname_stroke2 = strokes[1]
            if is_single_name:
                name_stroke1 = strokes[2]
                tian = surname_stroke1 + surname_stroke2
                ren = surname_stroke2 + name_stroke1
                di = name_stroke1 + 1
                wai = surname_stroke1 + 1
                zong = surname_stroke1 + surname_stroke2 + name_stroke1
            else:
                name_stroke1 = strokes[2]
                name_stroke2 = strokes[3]
                tian = surname_stroke1 + surname_stroke2
                ren = surname_stroke2 + name_stroke1
                di = name_stroke1 + name_stroke2
                wai = surname_stroke1 + name_stroke2
                zong = surname_stroke1 + surname_stroke2 + name_stroke1 + name_stroke2

        # 对81取余（超过81的减去80）
        def mod81(n):
            return n if n <= 81 else n - 80

        tian = mod81(tian)
        ren = mod81(ren)
        di = mod81(di)
        wai = mod81(wai)
        zong = mod81(zong)

        # 判断吉凶
        def get_luck(n):
            if n in cls.GREAT_LUCKY:
                return "大吉"
            elif n in cls.LUCKY_NUMBERS:
                return "吉"
            else:
                return "凶"

        result = {
            "tian_ge": {"value": tian, "luck": get_luck(tian)},
            "ren_ge": {"value": ren, "luck": get_luck(ren)},
            "di_ge": {"value": di, "luck": get_luck(di)},
            "wai_ge": {"value": wai, "luck": get_luck(wai)},
            "zong_ge": {"value": zong, "luck": get_luck(zong)},
        }

        # 总分计算
        # 人格权重最高（35%），总格次之（25%），天格地格各15%，外格10%
        def luck_score(luck):
            if luck == "大吉":
                return 100
            elif luck == "吉":
                return 80
            else:
                return 40

        total_score = (
            luck_score(result["ren_ge"]["luck"]) * 0.35
            + luck_score(result["zong_ge"]["luck"]) * 0.25
            + luck_score(result["tian_ge"]["luck"]) * 0.15
            + luck_score(result["di_ge"]["luck"]) * 0.15
            + luck_score(result["wai_ge"]["luck"]) * 0.10
        )

        result["total_score"] = round(total_score)
        result["description"] = cls._describe(result, total_score)

        return result

    @staticmethod
    def _describe(result: dict, score: float) -> str:
        """生成五格描述"""
        if score >= 85:
            return "五格数理配置优良，人格总格俱佳"
        elif score >= 70:
            return "五格数理尚可，人格为吉"
        elif score >= 55:
            return "五格数理一般，部分有凶"
        else:
            return "五格数理欠佳，建议调整"
