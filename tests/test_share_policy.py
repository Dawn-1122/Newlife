"""分享链路守卫测试。

存在的理由（两起真实事故）：

1. **`onShareAppMessage` 没有 `success` 回调。**
   官方返回值只支持 `title` / `path` / `imageUrl` / `promise`
   （框架接口 / Page，onShareAppMessage 小节）。
   `detail.js` 曾写成：
       onShareAppMessage() {
         return { title, path, success: () => this.markUnlocked() }
       }
   `success` 被**静默忽略** → `markUnlocked()` 永不执行 →
   「分享解锁深度寓意」整条链路是死的，且不报错、不崩溃、测试也不红，
   只有真机手点才发现。故用测试把这个坑封死。

2. **分享入口按页面随机缺失。**
   微信要求 `onShareAppMessage` 定义在页面里，右上角菜单才出现「转发」。
   此前 11 个页面里只有 4 个定义过，另外 7 个页面用户根本无法转发。

另含路由完整性检查（`/pages/...` 字面量必须在 app.json 里注册）。

实现说明：用「剥离 JS 注释与字符串后再做花括号配对」的办法取函数体，
不引入 JS 解析器依赖；剥离时**保持字符长度不变**，因此下标映射回原文仍然有效。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MINIPROGRAM = PROJECT_ROOT / "miniprogram"
APP_JSON = MINIPROGRAM / "app.json"
UTILS_DIR = MINIPROGRAM / "utils"

# 允许不支持分享的页面（纯重定向兜底页，onLoad 即跳走）
SHARE_EXEMPT_PAGES = {"pages/index/index"}


# --------------------------------------------------------------------------- #
# JS 源码处理
# --------------------------------------------------------------------------- #

def _strip_js(src: str) -> str:
    """把注释与字符串/模板字面量的**内容**替换为空格，长度与原串一致。

    这样既能安全做花括号配对（字符串里的括号不再干扰），
    又能用原串下标取回真实文本。
    """
    out: list[str] = []
    i, n = 0, len(src)
    state = None  # None | 'line' | 'block' | "'" | '"' | '`'
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if state is None:
            if ch == "/" and nxt == "/":
                state = "line"
                out.append("  ")
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block"
                out.append("  ")
                i += 2
                continue
            if ch in "'\"`":
                state = ch
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1
            continue

        if state == "line":
            if ch == "\n":
                state = None
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue

        if state == "block":
            if ch == "*" and nxt == "/":
                state = None
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        # 字符串 / 模板字面量内部
        if ch == "\\":
            out.append("  ")
            i += 2
            continue
        if ch == state:
            state = None
            out.append(ch)
            i += 1
            continue
        out.append("\n" if ch == "\n" else " ")
        i += 1

    return "".join(out)


def _match_pair(src: str, start: int, open_ch: str, close_ch: str) -> int | None:
    """返回 src[start] 处括号的配对位置下标（src 需已剥离字符串/注释）。"""
    if start >= len(src) or src[start] != open_ch:
        return None
    depth = 0
    for i in range(start, len(src)):
        if src[i] == open_ch:
            depth += 1
        elif src[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return None


def _method_bodies(src: str, name: str) -> list[str]:
    """取 `name(x) { ... }` 形式的函数体（已剥离注释字符串的源码）。"""
    bodies: list[str] = []
    for m in re.finditer(r"\b%s\s*\(" % re.escape(name), src):
        paren_end = _match_pair(src, m.end() - 1, "(", ")")
        if paren_end is None:
            continue
        brace_start = src.find("{", paren_end)
        if brace_start == -1:
            continue
        brace_end = _match_pair(src, brace_start, "{", "}")
        if brace_end is None:
            continue
        bodies.append(src[brace_start + 1:brace_end])
    return bodies


def _property_values(src: str, name: str) -> list[str]:
    """取 `name: <expr>,` 形式的取值表达式（已剥离注释字符串的源码）。"""
    values: list[str] = []
    for m in re.finditer(r"\b%s\s*:" % re.escape(name), src):
        seg = src[m.end():]
        cut = len(seg)
        for stop in (",", "\n", "}"):
            pos = seg.find(stop)
            if pos != -1:
                cut = min(cut, pos)
        values.append(seg[:cut])
    return values


# --------------------------------------------------------------------------- #
# 收集
# --------------------------------------------------------------------------- #

def _page_dirs() -> list[Path]:
    pages_root = MINIPROGRAM / "pages"
    return sorted(p for p in pages_root.iterdir() if p.is_dir())


def _page_js() -> list[Path]:
    return sorted((MINIPROGRAM / "pages").glob("*/*.js"))


def _all_js() -> list[Path]:
    return sorted(MINIPROGRAM.rglob("*.js"))


@pytest.fixture(scope="module")
def app_pages() -> list[str]:
    return json.loads(APP_JSON.read_text(encoding="utf-8"))["pages"]


# --------------------------------------------------------------------------- #
# 1. `success` 字段不存在（事故 ①）
# --------------------------------------------------------------------------- #

def test_no_success_field_in_inline_share_handlers():
    """任何页面里内联写的 onShareAppMessage，返回值都不得含 success 字段。"""
    offenders: list[str] = []
    for js in _page_js():
        src = _strip_js(js.read_text(encoding="utf-8"))
        for body in _method_bodies(src, "onShareAppMessage"):
            if re.search(r"\bsuccess\s*:", body):
                offenders.append(js.name)
    assert not offenders, (
        "以下页面在 onShareAppMessage 里返回了 success 字段 —— 该字段会被微信静默忽略，"
        f"对应逻辑永不执行：{offenders}"
    )


def test_no_success_field_in_share_util():
    """统一的分享实现（utils/share.js）同样不得含 success。"""
    src = _strip_js((UTILS_DIR / "share.js").read_text(encoding="utf-8"))
    assert not re.search(r"\bsuccess\s*:", src), (
        "utils/share.js 返回了 success 字段；该字段不被 onShareAppMessage 支持"
    )


def test_share_returns_only_supported_fields():
    """分享返回值只允许 title / path / imageUrl / promise 四个字段。"""
    allowed = {"title", "path", "imageUrl", "promise"}
    checked = 0
    for js in _all_js():
        src = _strip_js(js.read_text(encoding="utf-8"))
        for body in _method_bodies(src, "onShareAppMessage"):
            for key in re.findall(r"([A-Za-z_$][\w$]*)\s*:", body):
                assert key in allowed, (
                    f"{js.name} 的 onShareAppMessage 返回了不支持的字段 `{key}`"
                    f"（仅支持 {sorted(allowed)}）"
                )
            checked += 1
    assert checked >= 1, "没有扫到任何 onShareAppMessage 内联实现，测试可能已失效"


# --------------------------------------------------------------------------- #
# 2. 分享解锁链路的回归守卫（事故 ① 的修复不许被改回去）
# --------------------------------------------------------------------------- #

def test_detail_unlocks_when_share_initiated():
    """detail 页必须在分享发起时调用 markUnlocked()。"""
    src = _strip_js((MINIPROGRAM / "pages" / "detail" / "detail.js").read_text(encoding="utf-8"))
    bodies = _method_bodies(src, "onShareAppMessage") + _method_bodies(src, "onShareTimeline")
    assert bodies, "detail.js 找不到分享处理函数"
    assert any("markUnlocked" in b for b in bodies), (
        "detail.js 的分享处理函数里没有调用 markUnlocked()，"
        "分享解锁会再次失效（微信不提供分享成功回调，只能在发起时解锁）"
    )


def test_detail_unlock_batch_key_present():
    """解锁状态按起名批次记录，批次 id 缺失会退化成全局永久解锁。"""
    src = (MINIPROGRAM / "pages" / "detail" / "detail.js").read_text(encoding="utf-8")
    assert "lastBatchId" in src and "unlock_" in src, (
        "detail.js 的批次解锁键（unlock_ + lastBatchId）被破坏了"
    )


# --------------------------------------------------------------------------- #
# 3. 分享入口覆盖率 + 朋友圈（事故 ②）
# --------------------------------------------------------------------------- #

def test_every_page_defines_share_handler(app_pages):
    """除兜底重定向页外，每个页面都必须定义 onShareAppMessage。"""
    missing: list[str] = []
    for page in app_pages:
        if page in SHARE_EXEMPT_PAGES:
            continue
        src = _strip_js((MINIPROGRAM / (page + ".js")).read_text(encoding="utf-8"))
        if not (_method_bodies(src, "onShareAppMessage") or _property_values(src, "onShareAppMessage")):
            missing.append(page)
    assert not missing, (
        "以下页面未定义 onShareAppMessage，用户在这些页面的右上角菜单看不到「转发」："
        f"{missing}"
    )


def test_pages_with_share_also_define_timeline():
    """定义了 onShareAppMessage 的页面应同时支持分享到朋友圈。"""
    missing: list[str] = []
    for js in _page_js():
        src = _strip_js(js.read_text(encoding="utf-8"))
        has_share = bool(_method_bodies(src, "onShareAppMessage") or _property_values(src, "onShareAppMessage"))
        has_timeline = bool(_method_bodies(src, "onShareTimeline") or _property_values(src, "onShareTimeline"))
        if has_share and not has_timeline:
            missing.append(js.name)
    assert not missing, f"以下页面支持转发但不支持分享到朋友圈：{missing}"


# --------------------------------------------------------------------------- #
# 4. 路由完整性
# --------------------------------------------------------------------------- #

def test_page_files_complete(app_pages):
    """app.json 里注册的每个页面，四件套文件都要在。"""
    suffixes = [".js", ".json", ".wxml", ".wxss"]
    problems: list[str] = []
    for page in app_pages:
        for suffix in suffixes:
            if not (MINIPROGRAM / (page + suffix)).exists():
                problems.append(page + suffix)
    assert not problems, f"以下页面文件缺失：{problems}"


def test_referenced_routes_are_registered(app_pages):
    """代码/模板里出现的 `/pages/xxx/xxx` 路径都必须在 app.json 注册，防止跳转白屏。"""
    # app.json 的 pages 条目不带前导斜杠，跳转路径带 —— 统一成带斜杠再比
    registered = {"/" + p.lstrip("/") for p in app_pages}
    pattern = re.compile(r"/pages/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-]+")
    unknown: set[str] = set()
    for f in list(_all_js()) + sorted((MINIPROGRAM / "pages").glob("*/*.wxml")):
        for hit in pattern.findall(f.read_text(encoding="utf-8")):
            if hit not in registered:
                unknown.add(f"{f.name}: {hit}")
    assert not unknown, f"跳转到了未注册的页面路径：{sorted(unknown)}"


def test_share_util_exports_both_handlers():
    """utils/share.js 必须同时导出 defaultShare / defaultTimeline。"""
    src = _strip_js((UTILS_DIR / "share.js").read_text(encoding="utf-8"))
    assert re.search(r"defaultShare\s*[,:}]", src) or "defaultShare" in src
    assert "defaultTimeline" in src
    assert re.search(r"module\.exports", src)
