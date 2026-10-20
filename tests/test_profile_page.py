"""资料页与释名页的结构守卫测试。

钉住三件在后续改动里最容易悄悄丢掉的东西：

1. **不再用原生 `<picker>`。**
   预览环境里原生 picker 点不开 —— 用户选不了日期，点「下一步」只会收到
   「请选择出生日期」，看起来像起名坏了。日期与时辰改成自绘（三列 scroll-view
   + 点开式下拉），这条就是防止哪天有人「顺手改回原生组件更省事」。

2. **资料页不再分「已出生 / 未出生」两个 tab。**
   出生状态只影响八字，不影响姓氏、性别、字数；用 tab 逼用户先回答一个与当前
   操作无关的问题，是把结构成本转嫁给用户（用户 2026-10-20 拍板合并）。

3. **两页的日期/时辰交互必须共用同一份实现。**
   分头维护的下场是闰月、大小月、子时落在 23 点这类细节各说各话。

另外守住「视图与样式同源」：日期弹层 / 时辰下拉的样式只在 app.wxss 写一份 ——
它们全靠 position:fixed 撑着，样式一旦没加载就会掉回文档流，看上去就是
「点了没反应，页面底部多出一长串年份」。全局样式表每页必加载，比 @import 稳。
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
APP_WXSS = MINIPROGRAM / "app.wxss"

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
    assert "prenatal" in src, "name.js 不再区分「未出生」分支"
    # 孕期分支不问姓氏（只出五行参考，不出名字）
    assert re.search(r"if\s*\(!prenatal\)", src), (
        "姓氏校验没有排除孕期分支：未出生其实不需要姓氏"
    )
    assert "due_date" in src and "range_days" in src, "孕期分支的提交参数丢了"


# --------------------------------------------------------------------------- #
# 2b. 文案与控件形态（用户 2026-10-20 逐条点名的几条）
# --------------------------------------------------------------------------- #

def test_name_page_title_is_formal():
    wxml = _read(NAME_PAGE / "name.wxml")
    assert "填一下资料" not in wxml, (
        "页头又回到口语化的「填一下资料」：这一屏是个正式表单，标题该是「填写资料」一类"
    )
    assert "填写资料" in wxml


def test_name_page_says_weichusheng():
    """「还没出生」统一成「未出生」，与八字那句「宝宝出生了吗」呼应。"""
    wxml = _read(NAME_PAGE / "name.wxml")
    assert "还没出生" not in wxml, "页面里仍有「还没出生」，文案应统一为「未出生」"
    assert "未出生" in wxml


def test_name_page_placeholders_have_no_examples():
    """姓氏、字辈的占位符不写示例字。"""
    wxml = _read(NAME_PAGE / "name.wxml")
    for bad in ("如 沈", "如沈", "如 德", "如德"):
        assert bad not in wxml, f"占位符里仍有示例「{bad}」，用户明确要求去掉"
    # 占位符该给的是提示语，不是示例
    assert 'placeholder="请输入姓氏"' in wxml
    assert 'placeholder="选填"' in wxml


def test_hour_uses_the_same_sheet_as_date():
    """时辰与出生日期是同一种表现形式：点一行 → 底部弹层 → 确定回填。

    用户 2026-10-20 明确要求「时辰列表的表现形式跟出生日期保持一致」。
    别再改回 12 格平铺，也别改回行内下拉 —— 下拉向上开必盖住日期行、
    向下开必被屏幕底裁掉，两种都出过「点了没反应」。
    """
    for page in ("name", "analyze"):
        wxml = _read(PAGES / page / f"{page}.wxml")
        js = _read(PAGES / page / f"{page}.js")

        # 行内不能再有格子或下拉
        for legacy in ("hour-grid", "hour-cell", "select-panel", "select-trigger", "hourOpen"):
            assert legacy not in wxml, f"{page}.wxml 还留着旧的时辰控件 {legacy}"

        # 入口与日期行同款：整行可点 + 右端 › + 同一个弹层
        assert 'bindtap="onOpenHour"' in wxml, f"{page}.wxml 的时辰行没有开弹层"
        assert 'class="field-arrow"' in wxml, f"{page}.wxml 缺少右端箭头，和日期行不一致"
        assert "sheet.kind === 'hour'" in wxml, f"{page}.wxml 的弹层没有时辰分支"
        assert 'bindtap="onPickHour"' in wxml, f"{page}.wxml 缺少时辰选中"

        # 同一个 sheet 状态机，确定时按 kind 分流
        assert "onOpenHour" in js and "onPickHour" in js, f"{page}.js 缺少时辰弹层处理器"
        assert "kind: 'hour'" in js, f"{page}.js 打开时辰弹层时没标 kind"
        confirm = js[js.index("onSheetConfirm") : js.index("onSheetConfirm") + 600]
        assert "sheet.kind === 'hour'" in confirm, f"{page}.js 确定时没有按 kind 分流时辰"


def test_bazi_switch_is_a_square_ink_block():
    """八字开关是直角墨块，不是椭圆胶囊。

    胶囊形（50% 圆角）会把 84×44 的细长盒子拉成一条更扁的椭圆，白点落在浅色
    纸底上几乎没有对比，用户看到的就是「一处空白」（2026-10-20 要求换样式）。
    """
    app = _read(MINIPROGRAM / "app.wxss")
    track = re.search(r"^\.switch\s*\{(.*?)^\}", app, re.S | re.M)
    assert track, "app.wxss 找不到 .switch 定义"
    assert "50%" not in track.group(1), ".switch 用 50% 圆角会被拉成椭圆"
    assert "var(--r-sm)" in track.group(1), ".switch 应改用直角（--r-sm）"
    knob = re.search(r"^\.switch-knob\s*\{(.*?)^\}", app, re.S | re.M)
    assert knob, "app.wxss 找不到 .switch-knob 定义"
    assert "50%" not in knob.group(1), ".switch-knob 同样不能用 50% 圆角"
    assert re.search(r"^\.switch\.on\s*\{[^}]*var\(--ink\)", app, re.S | re.M), (
        "开启态应是实心墨块，才和关闭态形成明确对比"
    )


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


def test_sheet_styles_live_in_app_wxss():
    """日期弹层与时辰弹层的样式必须写在 app.wxss。

    这两块的全部观感都压在 `position: fixed` 上：样式没生效 → 弹层掉回文档流 →
    出生日期点开只是「页面底部多出一长串年份」，用户看到的是「点了没反应」。
    曾用 `@import "../../styles/x.wxss"` 共享，但 @import 是编译期行为，
    页面样式表 / 构建链 / 预览器任一处没展开就会复现上面那个坏样子。
    app.wxss 每页必加载，没有这层不确定性（2026-10-20 用户反馈后改）。
    """
    app = _read(APP_WXSS)
    for selector in (
        ".sheet-mask",
        ".sheet {",
        ".sheet-cols",
        ".sheet-item",
        ".sheet-cols-hour",
        ".sheet-item-hour",
        ".sheet-note",
        ".sheet-pad",
    ):
        assert selector in app, f"app.wxss 缺少 {selector} —— 浮层样式必须全局加载"

    # 弹层高度要有上限，否则窄视口会顶满整屏
    assert "max-height: 80vh" in app, ".sheet 没有高度上限，窄屏会顶满整屏"

    # 首尾衬垫：没有它，最后一项（今年）只能贴在最底边，往上拖也没有余量，
    # 看起来就像「日期列表拖不动」；有了衬垫，「今天」才会落在列的正中间。
    for page in ("name", "analyze"):
        wxml = _read(PAGES / page / f"{page}.wxml")
        assert 'class="sheet-pad"' in wxml, f"{page}.wxml 缺首尾衬垫，端点项无法居中"

    for page in ("name", "analyze"):
        wxss = _read(PAGES / page / f"{page}.wxss")
        assert '@import "' not in wxss, f"{page}.wxss 又用了 @import：浮层样式改由 app.wxss 全局加载"
        for selector in (".sheet-mask", ".sheet-cols", ".sheet-item", ".sheet-cols-hour", ".sheet-item-hour"):
            assert selector not in wxss, (
                f"{page}.wxss 又自己写了一份 {selector}：应与 app.wxss 保持一致"
            )


def test_preview_runner_inlines_wxss_import():
    """预览器必须能把 @import 内联掉（目前页面已不用 @import，留作兜底）。"""
    runner = _read(PROJECT_ROOT / "tools" / "preview" / "runner.js")
    assert "inlineWxssImports" in runner, "预览运行时不再展开 WXSS 的 @import"
    index = _read(PROJECT_ROOT / "tools" / "preview" / "index.html")
    assert "fromPath" in index, "预览外壳没把 fromPath 传给 transformWxss，@import 无法解析"


def test_preview_scroll_views_can_be_dragged():
    """预览里的 scroll-view 要能用鼠标拖。

    预览是手机形态，用户会按住列表往上拖；桌面浏览器不会因此滚动，反馈就是
    「列表滚不动」。index.html 里的拖拽垫片负责这件事（真机本来就能触摸滚动）。
    另外手机壳高度必须跟窗口走：写死高度时窗口一矮，底部弹层会落到可视区外，
    看上去同样像「滚不动」。
    """
    index = _read(PROJECT_ROOT / "tools" / "preview" / "index.html")
    assert "function enableDragScroll" in index, "预览器缺少 scroll-view 的拖拽滚动"
    assert re.search(r"^\s*enableDragScroll\(\)", index, re.M), "enableDragScroll 定义了却没调用"
    assert "closest('scroll-view')" in index, "拖拽滚动要限定在 scroll-view 上"

    phone = re.search(r"\.phone\s*\{(.*?)\}", index, re.S)
    assert phone, "index.html 找不到 .phone"
    assert "calc(100vh" in phone.group(1), "手机壳高度应随窗口变化，否则弹层会被顶出可视区"


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
