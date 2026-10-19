"""资料页与释名页的结构守卫测试。

钉住三件在后续改动里最容易悄悄丢掉的东西：

1. **不再用原生 `<picker>`。**
   预览环境里原生 picker 点不开 —— 用户选不了日期，点「下一步」只会收到
   「请选择出生日期」，看起来像起名坏了。日期与时辰改成自绘（三列 scroll-view
   + 十二时辰格），这条就是防止哪天有人「顺手改回原生组件更省事」。

2. **资料页不再分「已出生 / 未出生」两个 tab。**
   出生状态只影响八字，不影响姓氏、性别、字数；用 tab 逼用户先回答一个与当前
   操作无关的问题，是把结构成本转嫁给用户（用户 2026-10-20 拍板合并）。

3. **两页的日期/时辰交互必须共用同一份实现。**
   分头维护的下场是闰月、大小月、子时落在 23 点这类细节各说各话。

另外守住「视图与样式同源」：日期弹层 / 时辰格的样式只在 styles/ 下写一份，
页面通过 @import 引用 —— 预览器已支持 @import 内联，两处各抄一份必然走样。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MINIPROGRAM = PROJECT_ROOT / "miniprogram"
PAGES = MINIPROGRAM / "pages"
UTILS = MINIPROGRAM / "utils"
STYLES = MINIPROGRAM / "styles"

NAME_PAGE = PAGES / "name"
ANALYZE_PAGE = PAGES / "analyze"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. 不许再用原生 picker
# --------------------------------------------------------------------------- #

def test_name_page_has_no_native_picker():
    wxml = _read(NAME_PAGE / "name.wxml")
    assert "<picker" not in wxml, (
        "name.wxml 又用回原生 <picker>：预览里它点不开，用户选不了日期"
    )
    assert 'mode="date"' not in wxml
    assert 'mode="selector"' not in wxml


def test_analyze_page_has_no_native_picker():
    wxml = _read(ANALYZE_PAGE / "analyze.wxml")
    assert "<picker" not in wxml, (
        "analyze.wxml 又用回原生 <picker>：日历点不开，用户填不了生辰"
    )


def test_no_native_picker_anywhere():
    """整站扫一遍：其它页也别把原生 picker 带回来。"""
    offenders = []
    for path in MINIPROGRAM.rglob("*.wxml"):
        if "<picker" in _read(path):
            offenders.append(str(path.relative_to(MINIPROGRAM)))
    assert not offenders, "这些页面用了原生 <picker>（预览里点不开）：" + ", ".join(offenders)


# --------------------------------------------------------------------------- #
# 2. 资料页：一张表 + 八字开关驱动分支，没有 tab
# --------------------------------------------------------------------------- #

def test_name_page_has_no_tab_bar():
    wxml = _read(NAME_PAGE / "name.wxml")
    wxss = _read(NAME_PAGE / "name.wxss")
    assert "tab-bar" not in wxml and 'class="tab' not in wxml, (
        "资料页又出现了 tab：已出生/未出生应合并成「八字开关 + 出生状态」"
    )
    assert ".tab-bar" not in wxss and ".tab {" not in wxss


def test_name_page_switch_drives_birth_branch():
    """八字关 → 不追问出生状态；八字开 → 才出现「已出生 / 还没出生」。"""
    wxml = _read(NAME_PAGE / "name.wxml")
    assert 'wx:if="{{useBazi}}"' in wxml, "资料页没有用 useBazi 控制八字分支"
    # 出生状态两个选项必须在 useBazi 的分支里，不能无条件显示
    block_start = wxml.index('wx:if="{{useBazi}}"')
    born_idx = wxml.index("onBornTap")
    assert born_idx > block_start, (
        "「已出生 / 还没出生」跑到了八字开关外面：不选八字也被追问出生状态"
    )
    for handler in ("onOpenBirthDate", "onOpenDueDate"):
        assert handler in wxml, f"资料页缺少日期入口（{handler}）"


def test_name_page_js_splits_prenatal_branch():
    src = _read(NAME_PAGE / "name.js")
    assert "prenatal" in src, "name.js 不再区分「还没出生」分支"
    # 孕期分支不问姓氏（只出五行参考，不出名字）
    assert re.search(r"if\s*\(!prenatal\)", src), (
        "姓氏校验没有排除孕期分支：未出生其实不需要姓氏"
    )
    assert "due_date" in src and "range_days" in src, "孕期分支的提交参数丢了"


# --------------------------------------------------------------------------- #
# 3. 日期 / 时辰：一份实现，两页共用
# --------------------------------------------------------------------------- #

def test_date_sheet_data_layer_shared():
    assert (UTILS / "date-sheet.js").exists(), "缺少共用日期数据层 utils/date-sheet.js"
    src = _read(UTILS / "date-sheet.js")
    for fn in ("function build(", "function withYear(", "function withMonth(", "function format("):
        assert fn in src, f"date-sheet.js 缺 {fn}"

    for page in ("name", "analyze"):
        js = _read(PAGES / page / f"{page}.js")
        assert "utils/date-sheet" in js, f"{page}.js 没有用共用日期层，自己在算日期"
        assert "ds.build" in js, f"{page}.js 打开弹层时没有调 ds.build"


def test_hours_module_shared():
    assert (UTILS / "hours.js").exists(), "缺少共用时辰模块 utils/hours.js"
    src = _read(UTILS / "hours.js")
    # 十二时辰，且子时落在 23 点（跨日那一条最容易写错）
    assert src.count("label:") == 12, "十二时辰不是 12 项"
    assert "hour: 23" in src, "子时没有落在 23 点"

    for page in ("name", "analyze"):
        js = _read(PAGES / page / f"{page}.js")
        assert "utils/hours" in js, f"{page}.js 没有用共用时辰模块"


def test_sheet_styles_not_duplicated():
    """弹层与时辰格样式只在 styles/ 下写一份，页面用 @import 引用。"""
    for name in ("date-sheet.wxss", "hour-grid.wxss"):
        assert (STYLES / name).exists(), f"缺少共用样式 styles/{name}"

    for page in ("name", "analyze"):
        wxss = _read(PAGES / page / f"{page}.wxss")
        assert "../../styles/date-sheet.wxss" in wxss, f"{page}.wxss 没引用共用弹层样式"
        assert "../../styles/hour-grid.wxss" in wxss, f"{page}.wxss 没引用共用时辰格样式"
        # 页面里不该再定义一遍（出现即重复，改一处漏一处）
        for selector in (".sheet-mask", ".sheet-cols", ".sheet-item", ".hour-cell", ".hour-name"):
            assert selector not in wxss, (
                f"{page}.wxss 又自己写了一份 {selector}：应与 styles/ 下的共用样式保持一致"
            )


def test_preview_runner_inlines_wxss_import():
    """预览器必须能把 @import 内联掉，否则共用样式在预览里整段丢失。"""
    runner = _read(PROJECT_ROOT / "tools" / "preview" / "runner.js")
    assert "inlineWxssImports" in runner, "预览运行时不再展开 WXSS 的 @import"
    index = _read(PROJECT_ROOT / "tools" / "preview" / "index.html")
    assert "fromPath" in index, "预览外壳没把 fromPath 传给 transformWxss，@import 无法解析"


# --------------------------------------------------------------------------- #
# 4. 后端基址：探活必须校验响应体
# --------------------------------------------------------------------------- #

def test_api_probe_validates_health_body():
    src = _read(UTILS / "api.js")
    assert "isHealthy" in src, "api.js 的探活不再校验响应体"
    assert "status === 'ok'" in src, (
        "探活只看状态码是不够的：这台机器上 127.0.0.1 会被代理拦成"
        "「状态码 200 + 空响应」，只看 200 会错锁到一个拿不到数据的基址"
    )
    assert "API_PROBE_TIMEOUT" in src, "探活没有自带超时：宿主不实现 wx.request 的 timeout 时会挂死"
