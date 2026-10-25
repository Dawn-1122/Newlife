"""日期弹层数据层（miniprogram/utils/date-sheet.js）的行为测试。

为什么单独测这一层：起名页与释名页共用它，而三列滚选全靠 `*Anchor` 驱动
`scroll-into-view`。锚点一旦不同步，弹层会自己滚回旧位置 —— 用户看到的
就是「点 21 号，列表又跳回今天」，看着像点错了，其实数据是对的。

用 node 载入真实模块跑一遍（它不依赖 wx），把这类问题变成可执行断言。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DS_JS = PROJECT_ROOT / "miniprogram" / "utils" / "date-sheet.js"

_NODE = shutil.which("node") or shutil.which("nodejs")

_SCRIPT = r"""
const ds = require(process.argv[1])
const out = {}

// 闰年 2 月 + 锚点
const leap = ds.build({ value: '2020-02-29' })
out.leap = {
  days: leap.days.length,
  day: leap.day,
  anchors: [leap.yearAnchor, leap.monthAnchor, leap.dayAnchor]
}

// 换年：2/29 → 2021 年应收到 28 日，锚点同步
const y = ds.withYear(leap, 2021)
out.withYear = { days: y.days.length, day: y.day, anchor: y.dayAnchor }

// 换月：1/31 → 2 月应收到 28/29 日
const jan = ds.build({ value: '2021-01-31' })
const feb = ds.withMonth(jan, 2)
out.withMonth = { days: feb.days.length, day: feb.day, anchor: feb.dayAnchor }

// 选日：这一条是回归点 —— 只改 day 不改 dayAnchor，弹层会滚回旧位置
const picked = ds.withDay(jan, 21)
out.withDay = { day: picked.day, anchor: picked.dayAnchor }

// 选同一天也不能把锚点弄丢
const same = ds.withDay(jan, 31)
out.withDaySame = { day: same.day, anchor: same.dayAnchor }

// 默认值与格式化
const today = ds.today()
out.today = { text: today, shape: /^\d{4}-\d{2}-\d{2}$/.test(today) }
out.format = ds.format({ year: 2020, month: 2, day: 9 })
out.daysInMonth = [ds.daysInMonth(2020, 2), ds.daysInMonth(2021, 2), ds.daysInMonth(2021, 4)]
out.later = ds.daysLater(90)

// 未选过日期：用 fallback；给了非法值也不抛
const fromFallback = ds.build({ value: '', fallback: '2019-06-01' })
out.fallback = { y: fromFallback.year, m: fromFallback.month, d: fromFallback.day }
out.badValue = (function () {
  try { return ds.build({ value: '2019-13-40' }).month } catch (e) { return 'threw' }
})()

process.stdout.write(JSON.stringify(out))
"""


@pytest.fixture(scope="module")
def out() -> dict:
    if not _NODE:
        pytest.skip("未找到 node，跳过日期弹层测试")
    run = subprocess.run(
        [_NODE, "-e", _SCRIPT, str(DS_JS)],
        capture_output=True, text=True, timeout=30,
    )
    assert run.returncode == 0, f"node 执行失败：{run.stderr}"
    return json.loads(run.stdout)


def test_leap_year_has_29_days(out):
    assert out["leap"]["days"] == 29
    assert out["leap"]["day"] == 29
    assert out["leap"]["anchors"] == ["y2020", "m2", "d29"]


def test_year_change_clamps_day_and_anchor(out):
    """2/29 换到平年要收到 28 日，且锚点跟着改 —— 否则一换年就跳回旧日期。"""
    assert out["withYear"] == {"days": 28, "day": 28, "anchor": "d28"}


def test_month_change_clamps_day_and_anchor(out):
    assert out["withMonth"] == {"days": 28, "day": 28, "anchor": "d28"}


def test_pick_day_moves_anchor(out):
    """回归：点某一天后 dayAnchor 必须指到那一天。

    锚点不动时，`scroll-into-view` 仍是旧值，弹层会把列表滚回去 ——
    真机表现就是「点 21 号，又跳回今天」。
    """
    assert out["withDay"] == {"day": 21, "anchor": "d21"}


def test_pick_same_day_keeps_anchor(out):
    assert out["withDaySame"] == {"day": 31, "anchor": "d31"}


def test_today_shape_and_format(out):
    assert out["today"]["shape"] is True
    assert out["format"] == "2020-02-09"
    assert out["daysInMonth"] == [29, 28, 30]
    assert len(out["later"]) == 10


def test_empty_value_falls_back_and_bad_value_does_not_throw(out):
    """从没选过日期时用 fallback；传进非法值也只是夹紧，不许抛。"""
    assert out["fallback"] == {"y": 2019, "m": 6, "d": 1}
    assert out["badValue"] == 12
