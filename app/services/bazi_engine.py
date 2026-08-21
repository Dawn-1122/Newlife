"""
八字排盘引擎

功能：
1. 公历日期 → 农历日期转换
2. 四柱八字计算（年柱、月柱、日柱、时柱）
3. 五行统计分析（含藏干权重）
4. 喜用神判定（基于日主强弱和五行平衡）

参考：基于传统命理学规则，非简单"缺什么补什么"。
"""

from datetime import datetime, timedelta
from typing import Optional
from lunardate import LunarDate
from app.core.constants import (
    TIANGAN, DIZHI, TIANGAN_WUXING, DIZHI_WUXING,
    TIANGAN_YINYANG, DIZHI_CANGGAN,
    WUXING_SHENG, WUXING_KE, WUXING_LIST, DIZHI_SHENGXIAO,
)
from app.core.bazi_explanations import (
    WUXING_EXPLANATIONS, TIANGAN_EXPLANATIONS, DIZHI_EXPLANATIONS,
    PILLAR_EXPLANATIONS, CANGGAN_LEVELS, build_xiyong_explanation,
)


class BaziEngine:
    """八字排盘引擎"""

    # ── 公历转农历 ──

    @staticmethod
    def solar_to_lunar(year: int, month: int, day: int) -> LunarDate:
        """公历日期转农历日期"""
        return LunarDate.fromSolarDate(year, month, day)

    # ── 四柱计算 ──

    @staticmethod
    def _get_year_ganzhi(year: int) -> str:
        """
        年柱计算
        以立春为分界（简化处理：2月4日前后）
        注意：此为简化版，精确版需查立春时刻表
        """
        # 1984年甲子年为基准
        offset = (year - 1984) % 60
        gan = TIANGAN[offset % 10]
        zhi = DIZHI[offset % 12]
        return gan + zhi

    @staticmethod
    def _get_year_ganzhi_precise(dt: datetime) -> str:
        """年柱计算（含立春修正）"""
        year = dt.year
        # 简化：2月4日之前算上一年
        # 精确版应查当年立春精确时刻
        lichun_approx = datetime(year, 2, 4)
        if dt < lichun_approx:
            year -= 1
        return BaziEngine._get_year_ganzhi(year)

    @staticmethod
    def _get_month_ganzhi(dt: datetime, year_ganzhi: str) -> str:
        """
        月柱计算
        以节气为分界，非农历初一
        """
        year = dt.year
        month = dt.month
        day = dt.day

        # 月支对应表（以节气为准）
        # 寅月:立春~惊蛰, 卯月:惊蛰~清明, ...
        month_zhi_map = [
            (2, 4, "寅"),   # 立春
            (3, 6, "卯"),   # 惊蛰
            (4, 5, "辰"),   # 清明
            (5, 6, "巳"),   # 立夏
            (6, 6, "午"),   # 芒种
            (7, 7, "未"),   # 小暑
            (8, 8, "申"),   # 立秋
            (9, 8, "酉"),   # 白露
            (10, 8, "戌"),  # 寒露
            (11, 7, "亥"),  # 立冬
            (12, 7, "子"),  # 大雪
            (1, 6, "丑"),   # 小寒
        ]

        # 确定月支
        month_zhi = "丑"
        for m, d, zhi in month_zhi_map:
            if month == m:
                if day >= d:
                    month_zhi = zhi
                    break
                else:
                    # 取前一个月
                    idx = month_zhi_map.index((m, d, zhi))
                    month_zhi = month_zhi_map[(idx - 1) % 12][2]
                    break
        else:
            # 1月特殊处理
            if month == 1:
                if day >= 6:
                    month_zhi = "丑"
                else:
                    month_zhi = "子"

        # 月干：年干起月干
        # 甲己之年丙作首，乙庚之年戊为头，丙辛必定寻庚起，
        # 丁壬壬位顺行流，更有戊癸何方觅，甲寅之上好追求
        year_gan = year_ganzhi[0]
        month_gan_start = {
            "甲": "丙", "己": "丙",
            "乙": "戊", "庚": "戊",
            "丙": "庚", "辛": "庚",
            "丁": "壬", "壬": "壬",
            "戊": "甲", "癸": "甲",
        }
        start_gan = month_gan_start[year_gan]

        # 从寅月开始顺推
        zhi_index = DIZHI.index(month_zhi)
        # 寅的索引是2
        offset_from_yin = (zhi_index - 2) % 12
        start_gan_index = TIANGAN.index(start_gan)
        month_gan = TIANGAN[(start_gan_index + offset_from_yin) % 10]

        return month_gan + month_zhi

    @staticmethod
    def _get_day_ganzhi(dt: datetime) -> str:
        """
        日柱计算
        基准：1900年1月1日为甲戌日
        """
        base = datetime(1900, 1, 1)
        delta = (dt - base).days
        # 甲戌 = 天干索引0, 地支索引10
        gan_index = (0 + delta) % 10
        zhi_index = (10 + delta) % 12
        return TIANGAN[gan_index] + DIZHI[zhi_index]

    @staticmethod
    def _get_hour_ganzhi(dt: datetime, day_ganzhi: str) -> str:
        """
        时柱计算
        时辰：23-1子, 1-3丑, 3-5寅, ...
        """
        hour = dt.hour
        # 子时跨日：23点算次日子时
        if hour == 23:
            hour = -1  # 特殊处理

        hour_zhi_index = ((hour + 1) // 2) % 12
        hour_zhi = DIZHI[hour_zhi_index]

        # 时干：日干起时干
        # 甲己还加甲，乙庚丙作初，丙辛从戊起，
        # 丁壬庚子居，戊癸何方发，壬子是真途
        day_gan = day_ganzhi[0]
        hour_gan_start = {
            "甲": "甲", "己": "甲",
            "乙": "丙", "庚": "丙",
            "丙": "戊", "辛": "戊",
            "丁": "庚", "壬": "庚",
            "戊": "壬", "癸": "壬",
        }
        start_gan = hour_gan_start[day_gan]
        start_gan_index = TIANGAN.index(start_gan)
        hour_gan = TIANGAN[(start_gan_index + hour_zhi_index) % 10]

        return hour_gan + hour_zhi

    # ── 排盘主入口 ──

    @classmethod
    def generate_bazi(
        cls,
        year: int,
        month: int,
        day: int,
        hour: int = 12,
        minute: int = 0,
        gender: str = "male",
    ) -> dict:
        """
        生成完整八字排盘

        Args:
            year: 公历年
            month: 公历月
            day: 公历日
            hour: 小时（0-23）
            minute: 分钟
            gender: male / female

        Returns:
            八字排盘结果字典
        """
        dt = datetime(year, month, day, hour, minute)

        # 晚子时（23点）按次日排盘：日柱、时柱时干、年/月柱均以次日为基准
        bazi_dt = dt + timedelta(days=1) if hour == 23 else dt

        # 四柱
        year_gz = cls._get_year_ganzhi_precise(bazi_dt)
        month_gz = cls._get_month_ganzhi(bazi_dt, year_gz)
        day_gz = cls._get_day_ganzhi(bazi_dt)
        # 时支仍由原始时刻确定（23点为子时），时干按次日日干起算
        hour_gz = cls._get_hour_ganzhi(dt, day_gz)

        # 日主（日干）
        day_master = day_gz[0]
        day_master_wuxing = TIANGAN_WUXING[day_master]

        # 五行分析
        wuxing_analysis = cls._analyze_wuxing(year_gz, month_gz, day_gz, hour_gz)

        # 喜用神判定
        xiyong = cls._determine_xiyong(day_master, wuxing_analysis)
        xiyong["explanation"] = build_xiyong_explanation(xiyong)

        # 农历
        lunar = cls.solar_to_lunar(year, month, day)
        shengxiao = DIZHI_SHENGXIAO.get(year_gz[1], "")

        # 四柱详解
        pillars_detail = cls._build_pillars_detail(year_gz, month_gz, day_gz, hour_gz)

        # 五行详解
        wuxing_detail = cls._build_wuxing_detail(wuxing_analysis)

        return {
            "solar_date": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            "lunar_date": f"{lunar.year}年{lunar.month}月{lunar.day}日",
            "gender": gender,
            "shengxiao": shengxiao,
            "four_pillars": {
                "year": year_gz,
                "month": month_gz,
                "day": day_gz,
                "hour": hour_gz,
            },
            "pillars_detail": pillars_detail,
            "day_master": day_master,
            "day_master_wuxing": day_master_wuxing,
            "wuxing": wuxing_analysis,
            "wuxing_detail": wuxing_detail,
            "xiyong": xiyong,
        }

    # ── 解释组装 ──

    @staticmethod
    def _build_pillars_detail(
        year_gz: str, month_gz: str, day_gz: str, hour_gz: str
    ) -> list[dict]:
        """组装四柱详解（含天干地支五行、阴阳、藏干、柱位含义）"""
        positions = ["year", "month", "day", "hour"]
        ganzhis = [year_gz, month_gz, day_gz, hour_gz]
        detail = []

        for pos, gz in zip(positions, ganzhis):
            gan, zhi = gz[0], gz[1]
            gan_info = TIANGAN_EXPLANATIONS[gan]
            zhi_info = DIZHI_EXPLANATIONS[zhi]
            pillar_info = PILLAR_EXPLANATIONS[pos]

            # 地支藏干（本气/中气/余气）
            canggan = []
            for i, (cg, weight) in enumerate(DIZHI_CANGGAN[zhi]):
                level = CANGGAN_LEVELS[i] if i < len(CANGGAN_LEVELS) else ""
                canggan.append({
                    "gan": cg,
                    "wuxing": TIANGAN_WUXING[cg],
                    "level": level,
                })

            detail.append({
                "position": pos,
                "name": pillar_info["name"],
                "meaning": pillar_info["meaning"],
                "ganzhi": gz,
                "tian_gan": gan,
                "tian_gan_wuxing": gan_info["wuxing"],
                "tian_gan_yinyang": gan_info["yinyang"],
                "tian_gan_brief": gan_info["brief"],
                "tian_gan_detail": gan_info["detail"],
                "di_zhi": zhi,
                "di_zhi_wuxing": zhi_info["wuxing"],
                "di_zhi_yinyang": zhi_info["yinyang"],
                "di_zhi_shengxiao": zhi_info["shengxiao"],
                "di_zhi_brief": zhi_info["brief"],
                "di_zhi_detail": zhi_info["detail"],
                "canggan": canggan,
            })

        return detail

    @staticmethod
    def _build_wuxing_detail(wuxing_analysis: dict) -> list[dict]:
        """组装五行详解（含占比、五德、方位、季节、颜色、脏腑、释义）"""
        detail = []
        for w in WUXING_LIST:
            info = WUXING_EXPLANATIONS[w]
            detail.append({
                "name": w,
                "percent": wuxing_analysis["percentages"].get(w, 0),
                "count": round(wuxing_analysis["counts"].get(w, 0), 2),
                "nature": info["nature"],
                "direction": info["direction"],
                "season": info["season"],
                "color": info["color"],
                "organ": info["organ"],
                "brief": info["brief"],
                "detail": info["detail"],
            })
        return detail

    # ── 五行分析 ──

    @staticmethod
    def _analyze_wuxing(year_gz: str, month_gz: str, day_gz: str, hour_gz: str) -> dict:
        """
        五行统计分析（含藏干权重）

        统计四柱中各五行的力量值：
        - 天干：权重1.0
        - 地支本气：权重1.0
        - 地支中气：权重0.3
        - 地支余气：权重0.1
        """
        counts = {w: 0.0 for w in WUXING_LIST}

        pillars = [year_gz, month_gz, day_gz, hour_gz]

        for pillar in pillars:
            gan, zhi = pillar[0], pillar[1]

            # 天干五行
            gan_wx = TIANGAN_WUXING[gan]
            counts[gan_wx] += 1.0

            # 地支藏干五行
            for cang_gan, weight in DIZHI_CANGGAN[zhi]:
                cang_wx = TIANGAN_WUXING[cang_gan]
                counts[cang_wx] += weight

        # 归一化为百分比
        total = sum(counts.values())
        percentages = {w: round(counts[w] / total * 100, 1) for w in WUXING_LIST}

        # 缺失五行
        missing = [w for w in WUXING_LIST if counts[w] == 0]

        # 最弱五行
        weakest = min(WUXING_LIST, key=lambda w: counts[w])

        # 最强五行
        strongest = max(WUXING_LIST, key=lambda w: counts[w])

        return {
            "counts": counts,
            "percentages": percentages,
            "missing": missing,
            "weakest": weakest,
            "strongest": strongest,
            "total_strength": round(total, 2),
        }

    # ── 喜用神判定 ──

    @staticmethod
    def _determine_xiyong(day_master: str, wuxing_analysis: dict) -> dict:
        """
        喜用神判定（简化版）

        判定逻辑：
        1. 计算日主五行力量（同党五行 = 生我者 + 同我者）
        2. 判断日主强弱
        3. 身强：喜克泄耗（克我、我克、我生）
        4. 身弱：喜生扶（生我、同我）

        注意：此为简化版规则，精确版需考虑格局、调候、通关等
        """
        day_master_wx = TIANGAN_WUXING[day_master]

        # 同党五行：生我者 + 同我者
        # 生我：金生水→水生木→木生火→火生土→土生金
        sheng_me = {v: k for k, v in WUXING_SHENG.items()}
        helper_wx = sheng_me[day_master_wx]  # 生我的五行
        same_wx = day_master_wx               # 同我

        counts = wuxing_analysis["counts"]
        day_strength = counts[helper_wx] + counts[same_wx]
        total = wuxing_analysis["total_strength"]

        # 身强/身弱判定（简化：日主力量 > 总力量的40%为身强）
        strength_ratio = day_strength / total if total > 0 else 0
        is_strong = strength_ratio > 0.4

        if is_strong:
            # 身强：喜克泄耗
            ke_me = WUXING_KE[day_master_wx]   # 克我的五行（官杀）
            i_ke = {v: k for k, v in WUXING_KE.items()}[day_master_wx]  # 我克的五行（财星）
            i_sheng = WUXING_SHENG[day_master_wx]  # 我生的五行（食伤）
            xi_wuxing = [ke_me, i_ke, i_sheng]
            yong_wuxing = ke_me  # 用神取最有力的一项
        else:
            # 身弱：喜生扶
            xi_wuxing = [helper_wx, same_wx]
            yong_wuxing = helper_wx

        # 忌神
        ji_wuxing = [w for w in WUXING_LIST if w not in xi_wuxing]

        return {
            "day_master": day_master,
            "day_master_wuxing": day_master_wx,
            "is_strong": is_strong,
            "strength_label": "身强" if is_strong else "身弱",
            "strength_ratio": round(strength_ratio * 100, 1),
            "xi_wuxing": xi_wuxing,       # 喜神五行
            "yong_wuxing": yong_wuxing,    # 用神五行
            "ji_wuxing": ji_wuxing,        # 忌神五行
        }
