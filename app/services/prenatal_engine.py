"""
预产期历法参考引擎（孕期范围 / 五行分布）

核心思路：预产期未出生、时辰未知，无法精确排盘，因此不做确定性排盘，
而是以预产期为中心遍历 `[due_date - range_days, due_date + range_days]` 每一天，
每天用固定 `hour=12`（午时）调用 `BaziEngine.generate_bazi`，
数出「日柱天干五行」各出现多少天，归一化为占比。

合规口径（2026-10-25）：只出历法事实与计数，不预测命理、不提供建议。
所以这里不计算喜用神分布，也不产出「稳定五行 / 候选字 / 结论文案」——
给未出生的孩子推断喜用五行，本身就是预测命理。
"""

from collections import Counter
from datetime import datetime, timedelta

from app.core.constants import (
    WUXING_LIST,
    DEFAULT_RANGE_DAYS,
    DIZHI_WUXING,
)
from app.services.bazi_engine import BaziEngine


class PrenatalEngine:
    """预产期历法参考引擎"""

    def __init__(self):
        self.bazi = BaziEngine()

    def generate(
        self,
        due_date: str,
        range_days: int = DEFAULT_RANGE_DAYS,
    ) -> dict:
        """
        生成预产期范围的历法参考

        Args:
            due_date: 预产期，格式 YYYY-MM-DD
            range_days: 前后浮动天数，取值 0|3|7|14

        Returns:
            {
                "due_date": str,
                "range_days": int,
                "range": {"start": str, "end": str},
                "certain": {"shengxiao": str, "month_ganzhi": str, "month_wuxing": str},
                "probabilistic": {
                    "day_master_wuxing_dist": {五行: 0~1},
                },
            }
        """
        due = self._parse_date(due_date)

        dates = self._sample_dates(due, range_days)
        day_master_dist = self._aggregate(dates)

        return {
            "due_date": due.strftime("%Y-%m-%d"),
            "range_days": range_days,
            "range": {
                "start": dates[0].strftime("%Y-%m-%d"),
                "end": dates[-1].strftime("%Y-%m-%d"),
            },
            "certain": self._build_certain(due),
            "probabilistic": {
                "day_master_wuxing_dist": day_master_dist,
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

    def _aggregate(self, dates) -> dict:
        """
        遍历每天采样排盘，数出日柱天干五行的出现天数，归一化为占比。

        分母 = 采样天数。这是纯计数，不含任何「哪种五行更好」的判断。
        """
        counter = Counter()

        for d in dates:
            bazi = self.bazi.generate_bazi(d.year, d.month, d.day, hour=12, minute=0)
            counter[bazi["day_master_wuxing"]] += 1

        return {w: (counter.get(w, 0) / len(dates)) for w in WUXING_LIST}

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
