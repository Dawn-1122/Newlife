"""视觉令牌守卫测试。

`docs/visual_system.md` 与 `miniprogram/app.wxss` 顶部注释共同声明了一条长期规则：

> **改视觉只改 `app.wxss` 的令牌，页面样式一律引用变量，不写死颜色。**

但 2026-10-13 实测：7 个二级页面里仍有 **241 处**硬编码色值（analyze / analyze-result /
bazi / detail / index / prenatal-result / result），只是它们的取值恰好等于令牌值 ——
所以「改令牌」对这些页面**完全不生效**，肉眼也看不出问题，属于最难发现的漂移。

本测试把该规则变成可执行约束：颜色只允许出现在 `app.wxss` 里。
同一批约束还覆盖 `docs/visual_system.md` 的另外三条硬规则：
不用阴影、圆角收敛（禁 16rpx 以上与胶囊）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MINIPROGRAM = PROJECT_ROOT / "miniprogram"
APP_WXSS = MINIPROGRAM / "app.wxss"

HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
VAR_USE_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_\-]+)")
VAR_DEF_RE = re.compile(r"^\s*(--[A-Za-z0-9_\-]+)\s*:", re.MULTILINE)
RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;]+);")

# docs/visual_system.md 第二节列出的令牌，缺一个都会让页面变量解析失败
REQUIRED_TOKENS = {
    "--paper", "--paper-deep", "--card",
    "--ink", "--ink-2", "--ink-3",
    "--line", "--line-strong",
    "--cinnabar", "--cinnabar-bg",
    "--r-sm", "--r-md", "--serif",
    "--wx-jin", "--wx-mu", "--wx-shui", "--wx-huo", "--wx-tu",
}


def _all_wxss() -> list[Path]:
    return sorted(MINIPROGRAM.rglob("*.wxss"))


def _page_wxss() -> list[Path]:
    return [p for p in _all_wxss() if "pages" in p.parts]


@pytest.fixture(scope="module")
def app_src() -> str:
    return APP_WXSS.read_text(encoding="utf-8")


def test_no_raw_hex_in_page_wxss():
    """页面样式不得写死颜色 —— 只允许引用 var(--token)。"""
    offenders: list[str] = []
    for f in _page_wxss():
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for hit in HEX_RE.findall(line):
                offenders.append(f"{f.relative_to(MINIPROGRAM)}:{lineno} {hit}")
    assert not offenders, (
        "以下页面样式写死了颜色（应改为 var(--token)，否则改 app.wxss 令牌对这些页面不生效）："
        f"{offenders}"
    )


def test_every_used_var_is_defined(app_src):
    """所有被引用的 CSS 变量都必须在 app.wxss 里定义过。"""
    defined = set(VAR_DEF_RE.findall(app_src))
    missing: set[str] = set()
    for f in _all_wxss():
        for name in VAR_USE_RE.findall(f.read_text(encoding="utf-8")):
            if name not in defined:
                missing.add(f"{f.relative_to(MINIPROGRAM)}: {name}")
    assert not missing, f"引用了未定义的令牌：{sorted(missing)}"


def test_every_defined_var_is_used(app_src):
    """定义了却没人用的令牌 = 死代码，会让人误以为改了有用。"""
    used: set[str] = set()
    for f in _all_wxss():
        used.update(VAR_USE_RE.findall(f.read_text(encoding="utf-8")))
    dead = set(VAR_DEF_RE.findall(app_src)) - used - {"--serif"}
    assert not dead, f"以下令牌已定义但全站无人引用：{sorted(dead)}"


def test_required_tokens_present(app_src):
    """规范文档列出的令牌必须齐备。"""
    defined = set(VAR_DEF_RE.findall(app_src))
    assert not (REQUIRED_TOKENS - defined), (
        f"app.wxss 缺少规范要求的令牌：{sorted(REQUIRED_TOKENS - defined)}"
    )


def test_no_box_shadow():
    """硬规则②：不用阴影，用细线 + 留白分层。"""
    offenders = [
        str(f.relative_to(MINIPROGRAM))
        for f in _all_wxss()
        if "box-shadow" in f.read_text(encoding="utf-8")
    ]
    assert not offenders, f"以下样式用了 box-shadow（违反「不用阴影」）：{offenders}"


def test_border_radius_within_limit():
    """硬规则③：圆角收敛 —— 禁 16rpx 以上与胶囊。"""
    offenders: list[str] = []
    for f in _all_wxss():
        for line in f.read_text(encoding="utf-8").splitlines():
            m = RADIUS_RE.search(line)
            if not m:
                continue
            value = m.group(1)
            for num in re.findall(r"(\d+(?:\.\d+)?)rpx", value):
                if float(num) > 16:
                    offenders.append(f"{f.relative_to(MINIPROGRAM)}: {value.strip()}")
            # 胶囊：超大值或百分比（50% 仅允许真正的圆形符号，由 wuxing 圆点使用）
            for num in re.findall(r"(\d+(?:\.\d+)?)px", value):
                if float(num) > 16:
                    offenders.append(f"{f.relative_to(MINIPROGRAM)}: {value.strip()}")
            if re.search(r"\d{3,}rpx|9999|\b\dp\b", value):
                offenders.append(f"{f.relative_to(MINIPROGRAM)}: {value.strip()}")
    assert not offenders, f"以下圆角违反「禁 16rpx 以上与胶囊」：{offenders}"


def test_wuxing_colors_are_mineral_not_material(app_src):
    """五行必须用传统矿物色，不得回落 Material 色。"""
    material = {"#4CAF50", "#2196F3", "#FF5722", "#FFC107", "#9C27B0", "#00BCD4"}
    used = {h.upper() for h in HEX_RE.findall(app_src)}
    assert not (material & used), f"app.wxss 里出现了 Material 色：{sorted(material & used)}"
    for token in ("--wx-jin", "--wx-mu", "--wx-shui", "--wx-huo", "--wx-tu"):
        assert token in app_src, f"缺少五行令牌 {token}"
