"""
预产期起名引擎（孕期参考 / 范围建议）

核心思路：预产期未出生、时辰未知，无法精确排盘，因此不做确定性排盘，
而是以预产期为中心遍历 `[due_date - range_days, due_date + range_days]` 每一天，
每天用固定 `hour=12`（午时）调用近似版 `BaziEngine.generate_bazi`，
聚合「日主五行」与「喜用神五行」的频次，归一化为概率分布。
"""

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from app.core.constants import (
    WUXING_LIST,
    NEGATIVE_CHARS,
    DEFAULT_RANGE_DAYS,
    DIZHI_WUXING,
)
from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase


class PrenatalEngine:
    """预产期起名引擎"""

    # 稳定五行概率阈值：喜用神分布中概率 >= 该值的五行才纳入建议
    STABLE_WUXING_THRESHOLD = 0.15
    # 每个稳定五行取的安全候选字数量上限
    SAFE_CHARS_PER_WUXING = 6

    def __init__(self):
        self.bazi = BaziEngine()
        self.char_db = CharDatabase()

    def generate(
        self,
        due_date: str,
        range_days: int = DEFAULT_RANGE_DAYS,
        gender: str = "male",
    ) -> dict:
        """
        生成预产期起名建议

        Args:
            due_date: 预产期，格式 YYYY-MM-DD
            range_days: 前后浮动天数，取值 0|3|7|14
            gender: male / female

        Returns:
            {
                "due_date": str,
                "range_days": int,
                "range": {"start": str, "end": str},
                "certain": {"shengxiao": str, "month_ganzhi": str, "month_wuxing": str},
                "probabilistic": {
                    "day_master_wuxing_dist": {五行: 0~1},
                    "xiyong_wuxing_dist": {五行: 0~1},
                },
                "suggestion": {
                    "stable_wuxing": [str, ...],
                    "safe_chars": [{...}, ...],
                    "note": str,
                },
            }
        """
        due = self._parse_date(due_date)

        dates = self._sample_dates(due, range_days)
        day_master_dist, xiyong_dist = self._aggregate(dates, gender)

        certain = self._build_certain(due)
        stable_wuxing = self._pick_stable_wuxing(xiyong_dist)
        safe_chars = self._build_safe_chars(stable_wuxing, gender)
        note = self._build_note(
            due, range_days, certain, xiyong_dist, stable_wuxing
        )

        return {
            "due_date": due.strftime("%Y-%m-%d"),
            "range_days": range_days,
            "range": {
                "start": dates[0].strftime("%Y-%m-%d"),
                "end": dates[-1].strftime("%Y-%m-%d"),
            },
            "certain": certain,
            "probabilistic": {
                "day_master_wuxing_dist": day_master_dist,
                "xiyong_wuxing_dist": xiyong_dist,
            },
            "suggestion": {
                "stable_wuxing": stable_wuxing,
                "safe_chars": safe_chars,
                "note": note,
            },
        }

    # ── 采样 ──

    @staticmethod
    def _parse_date(due_date: str) -> "datetime.date":
        """解析预产期字符串，非法格式抛出 ValueError"""
        try:
            return datetime.strptime(due_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError(f"预产期格式应为 YYYY-MM-DD，收到：{due_date}")

    @staticmethod
    def _sample_dates(due: "datetime.date", range_days: int):
        """生成采样日期列表 [due - range_days ... due + range_days]"""
        return [due + timedelta(days=offset) for offset in range(-range_days, range_days + 1)]

    def _aggregate(self, dates, gender: str):
        """
        遍历每天采样排盘，聚合日主/喜用神五行频次，归一化为概率分布。

        day_master_dist 分母 = 采样天数；
        xiyong_dist 分母 = 喜用神总票数（身强身弱喜神个数不同，不能简单除以天数）。
        """
        day_master_counter = Counter()
        xiyong_counter = Counter()
        total_xi_votes = 0

        for d in dates:
            bazi = self.bazi.generate_bazi(
                d.year, d.month, d.day, hour=12, minute=0, gender=gender
            )
            day_master_counter[bazi["day_master_wuxing"]] += 1
            for w in bazi["xiyong"]["xi_wuxing"]:
                xiyong_counter[w] += 1
                total_xi_votes += 1

        day_master_dist = {
            w: (day_master_counter.get(w, 0) / len(dates)) for w in WUXING_LIST
        }
        xiyong_dist = {
            w: (xiyong_counter.get(w, 0) / total_xi_votes if total_xi_votes else 0.0)
            for w in WUXING_LIST
        }
        return day_master_dist, xiyong_dist

    # ── 确定性结果 ──

    def _build_certain(self, due: "datetime.date") -> dict:
        """取预产期当天排盘的确定性结果：生肖 + 月柱干支 + 月柱五行"""
        bazi = self.bazi.generate_bazi(due.year, due.month, due.day, hour=12)
        month_ganzhi = bazi["four_pillars"]["month"]
        month_zhi = month_ganzhi[1]
        return {
            "shengxiao": bazi["shengxiao"],
            "month_ganzhi": month_ganzhi,
            "month_wuxing": DIZHI_WUXING.get(month_zhi, "未知"),
        }

    # ── 建议生成 ──

    def _pick_stable_wuxing(self, xiyong_dist: dict) -> list[str]:
        """喜用神分布中概率最高且 >= 阈值的 Top2 五行"""
        ranked = sorted(
            xiyong_dist.items(), key=lambda kv: kv[1], reverse=True
        )
        stable = [w for w, p in ranked if p >= self.STABLE_WUXING_THRESHOLD]
        return stable[:2]

    def _build_safe_chars(self, stable_wuxing: list[str], gender: str) -> list[dict]:
        """稳定五行对应的吉字候选（每个五行取 <=6 个，luck==吉 且性别匹配、非负面字）"""
        safe_chars = []
        for wuxing in stable_wuxing:
            chars = self.char_db.get_lucky_by_wuxing(
                wuxing, gender, limit=self.SAFE_CHARS_PER_WUXING
            )
            for c in chars:
                if c["char"] in NEGATIVE_CHARS:
                    continue
                safe_chars.append({
                    "char": c["char"],
                    "pinyin": c["pinyin"],
                    "wuxing": c["wuxing"],
                    "kangxi_strokes": c["kangxi_strokes"],
                    "meaning": c.get("meaning", ""),
                    "luck": c.get("luck", ""),
                })
        return safe_chars

    def _build_note(
        self,
        due: "datetime.date",
        range_days: int,
        certain: dict,
        xiyong_dist: dict,
        stable_wuxing: list[str],
    ) -> str:
        """组装面向用户的说明文案（含免责声明）"""
        start = (due - timedelta(days=range_days)).strftime("%m/%d")
        end = (due + timedelta(days=range_days)).strftime("%m/%d")

        top_parts = []
        for w in stable_wuxing:
            pct = int(round(xiyong_dist.get(w, 0.0) * 100))
            top_parts.append(f"{w}{pct}%")

        stable_text = "、".join(stable_wuxing) if stable_wuxing else "综合"
        top_text = "、".join(top_parts) if top_parts else "暂无明显倾向"

        return (
            f"预产期附近（{start}~{end}）出生，生肖为{certain['shengxiao']}，"
            f"月柱{certain['month_ganzhi']}属{certain['month_wuxing']}。"
            f"喜用神五行以{stable_text}概率最高（{top_text}），"
            f"建议名字优先用{stable_text}属性字，避开忌神对应的过强五行。"
            f"数据为孕期范围参考，出生后可精确起名复核。"
        )
