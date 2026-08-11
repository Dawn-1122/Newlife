"""
音律评分模块

分析名字的声调搭配，避免全平或全仄，给出音律评分。
"""

from pypinyin import pinyin, Style


class PhoneticsScorer:
    """音律评分器"""

    # 声调分类：1声2声为平，3声4声为仄
    TONE_TYPES = {
        1: "平", 2: "平",
        3: "仄", 4: "仄",
        0: "轻",  # 轻声
    }

    @classmethod
    def get_pinyin(cls, char: str) -> tuple[str, int]:
        """获取汉字拼音和声调"""
        py = pinyin(char, style=Style.TONE, heteronym=False)
        if not py or py[0][0] == char:
            return char, 0

        result = py[0][0]
        # 提取声调数字
        tone = 0
        for c in result:
            if c in "āáǎà":
                tone = 1 if c == "ā" else 2 if c == "á" else 3 if c == "ǎ" else 4
                break
            elif c in "ēéěè":
                tone = 1 if c == "ē" else 2 if c == "é" else 3 if c == "ě" else 4
                break
            elif c in "īíǐì":
                tone = 1 if c == "ī" else 2 if c == "í" else 3 if c == "ǐ" else 4
                break
            elif c in "ōóǒò":
                tone = 1 if c == "ō" else 2 if c == "ó" else 3 if c == "ǒ" else 4
                break
            elif c in "ūúǔù":
                tone = 1 if c == "ū" else 2 if c == "ú" else 3 if c == "ǔ" else 4
                break
            elif c in "ǖǘǚǜ":
                tone = 1 if c == "ǖ" else 2 if c == "ǘ" else 3 if c == "ǚ" else 4
                break

        return result, tone

    @classmethod
    def analyze(cls, name: str) -> dict:
        """
        分析名字音律

        Returns:
            {
                "pinyins": ["zhāng", "wěi"],
                "tones": [1, 3],
                "tone_types": ["平", "仄"],
                "rhythm": "平仄",  # 声调搭配模式
                "score": 85,  # 音律评分 0-100
                "description": "平仄相间，音韵和谐"
            }
        """
        chars = list(name)
        pinyins = []
        tones = []
        tone_types = []

        for c in chars:
            py, tone = cls.get_pinyin(c)
            pinyins.append(py)
            tones.append(tone)
            tone_types.append(cls.TONE_TYPES.get(tone, "轻"))

        # 评分逻辑
        score = cls._calculate_score(tones, tone_types)
        description = cls._describe(tone_types, score)

        # 声调搭配模式
        rhythm = "".join(tone_types)

        return {
            "pinyins": pinyins,
            "tones": tones,
            "tone_types": tone_types,
            "rhythm": rhythm,
            "score": score,
            "description": description,
        }

    @staticmethod
    def _calculate_score(tones: list[int], tone_types: list[str]) -> int:
        """计算音律评分"""
        if len(tones) < 2:
            return 70

        score = 70  # 基础分

        # 平仄相间加分
        unique_types = set(tone_types)
        if len(unique_types) >= 2:
            score += 15  # 有平有仄

        # 声调不全相同加分
        if len(set(tones)) >= 2:
            score += 10

        # 三字名额外检查
        if len(tones) == 3:
            # 平仄平 或 仄平仄 最佳
            if tone_types[0] != tone_types[1] and tone_types[1] != tone_types[2]:
                score += 5
            # 全平或全仄扣分
            if len(unique_types) == 1:
                score -= 20

        # 避免连续同声调
        for i in range(len(tones) - 1):
            if tones[i] == tones[i + 1] and tones[i] != 0:
                score -= 3

        return max(0, min(100, score))

    @staticmethod
    def _describe(tone_types: list[str], score: int) -> str:
        """生成音律描述"""
        if score >= 90:
            return "平仄协调，音韵优美，朗朗上口"
        elif score >= 75:
            return "声调搭配和谐，读来顺口"
        elif score >= 60:
            return "音律尚可，略有平淡"
        else:
            return "声调单一，建议调整搭配"
