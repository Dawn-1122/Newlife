"""女性 × 偏好 场景下，带宽开启/关闭的输出对比（确认改动未劣化女性向结果）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.naming_engine import NamingEngine  # noqa: E402

CASES = [
    ("林", "female", 2020, 8, 20, ["beauty", "wisdom"]),
    ("苏", "female", 2019, 3, 15, ["gentle"]),
    ("林", "female", 2020, 8, 20, None),
]

for (surname, gender, y, m, d, meanings) in CASES:
    print("=" * 70)
    print(f"{surname} {gender} {y}-{m:02d}-{d:02d} 偏好={meanings}")
    for label, band in (("带宽18(现设置)", 18.0), ("带宽0(原设置)", 0.0)):
        NamingEngine.STRATIFY_QUALITY_BAND = band
        eng = NamingEngine()
        r = eng.generate_names(surname, gender, y, m, d, 12, 0, name_length=2,
                               max_results=10, meanings=meanings)
        out = "、".join(
            f'{n["full_name"]}({round(n["scores"]["yunwei"])})'
            for n in r["names"])
        print(f"  {label}: {out}")
    print()
