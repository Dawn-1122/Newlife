"""分享落地页（/pages/share/share）守卫测试。

存在的理由：分享是唯一的外部流量入口，它坏掉**不会报错**，只会悄悄少掉一半人。
本文件钉住三件在后续改动里最容易丢的东西：

1. **落地页必须能用 URL 参数重建内容。**
   detail 页依赖 `app.globalData.selectedName`，好友冷启动点开分享卡时该数据不存在，
   `onLoad` 会直接 `navigateBack` —— 也就是说把 detail 当落地页，好友看到的是白屏。
   这条曾经就是线上状态（detail 的分享 path 写死成 `/pages/home/home`）。

2. **分享卡与落地页的出处必须是同一首。**
   生成器给名字配出处用的是「本次生成上下文里的那一条」，落地页只剩名字，
   重新解析可能落到另一首同样含名字用字的诗。故出处随链接带走，不许落地页重新猜。

3. **不显示评分。**
   推荐分只用于起名时的排序；落到详情页/落地页上就成了给名字定三六九等
   ——「每个人的名字都值得被喜爱」（用户 2026-10-19 拍板）。
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MINIPROGRAM = PROJECT_ROOT / "miniprogram"
APP_JSON = MINIPROGRAM / "app.json"
UTILS = MINIPROGRAM / "utils"
PAGES = MINIPROGRAM / "pages"

SHARE_PAGE = "pages/share/share"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_pages() -> list[str]:
    return json.loads(_read(APP_JSON))["pages"]


# --------------------------------------------------------------------------- #
# 1. 落地页存在且被注册
# --------------------------------------------------------------------------- #

def test_share_page_registered(app_pages):
    assert SHARE_PAGE in app_pages, (
        "app.json 未注册 pages/share/share：分享路径会跳到未注册页面，好友点开即白屏"
    )


def test_share_page_files_complete():
    for suffix in (".js", ".json", ".wxml", ".wxss"):
        assert (MINIPROGRAM / (SHARE_PAGE + suffix)).exists(), f"分享页缺文件 {suffix}"


# --------------------------------------------------------------------------- #
# 2. 分享路径指向落地页，且带得上名字
# --------------------------------------------------------------------------- #

def test_share_util_points_to_share_page():
    src = _read(UTILS / "share.js")
    assert re.search(r"NAME_PATH\s*=\s*'/pages/share/share'", src), (
        "utils/share.js 的 NAME_PATH 不再指向 /pages/share/share —— "
        "名字分享会退回到一个读不出内容的页面"
    )
    # nameShare 必须用 NAME_PATH 拼路径，不能另写一份字面量
    body = src[src.index("function nameShare("):]
    assert "NAME_PATH" in body, "nameShare 没有用 NAME_PATH 组包，路径口径会漂移"


def test_share_query_carries_name_and_poem():
    src = _read(UTILS / "share.js")
    body = src[src.index("function nameShareQuery("):src.index("function nameShareTitle(")]
    assert "'n='" in body, "分享参数丢了 n（姓名），落地页无从重建"
    # 出处三项：citation / 原句 / 作者朝代
    for key in ("'c='", "'x='"):
        assert key in body, f"分享参数丢了 {key}：落地页会用同名重新解析出另一首诗"


def test_detail_share_uses_name_share():
    src = _read(PAGES / "detail" / "detail.js")
    body = src[src.index("onShareAppMessage()"):]
    body = body[:body.index("onShareTimeline")]
    assert "share.nameShare" in body, (
        "detail 的 onShareAppMessage 没有走 utils/share.nameShare —— "
        "分享卡会再次丢掉「他分享的是哪个名字」"
    )
    assert "share.markUnlocked" not in body  # 防止误写成 util 方法
    assert "markUnlocked" in body, "分享解锁链路断了"
    assert "/pages/home/home" not in body, (
        "detail 的分享路径又写死回首页了：收到分享的人点开看到的不是那个名字"
    )


# --------------------------------------------------------------------------- #
# 3. 不显示评分（产品原则）
# --------------------------------------------------------------------------- #

def test_detail_page_has_no_overall_score():
    wxml = _read(PAGES / "detail" / "detail.wxml")
    assert "综合评分" not in wxml, "detail 页又把「综合评分」加回来了（用户已拍板去掉）"
    assert "scores.overall" not in wxml, "detail 页仍在渲染 scores.overall"

    js = _read(PAGES / "detail" / "detail.js")
    assert "scores.overall" not in js, (
        "detail.js 仍在读 scores.overall（复制文案 / 分享标题）—— "
        "分数不该出现在用户会带走的文字里"
    )


def test_share_page_has_no_score():
    for name in ("share.wxml", "share.js"):
        content = _read(PAGES / "share" / name)
        assert "scores" not in content, f"{name} 出现了 scores：落地页不显示任何评分"


# --------------------------------------------------------------------------- #
# 4. 落地页的关键构件
# --------------------------------------------------------------------------- #

def test_share_page_has_qrcode_slot():
    wxml = _read(PAGES / "share" / "share.wxml")
    assert "qr-block" in wxml and "qrUrl" in wxml, (
        "分享页的小程序码位被删了：分享页要预留小程序码的位置"
    )
    assert "show-menu-by-longpress" in wxml, (
        "小程序码图缺 show-menu-by-longpress，长按无法识别"
    )


def test_share_page_has_two_ctas(app_pages):
    """双 CTA：主「我也要起名」+ 次「释名 · 测测我的名字」。"""
    wxml = _read(PAGES / "share" / "share.wxml")
    js = _read(PAGES / "share" / "share.js")

    for handler in ("onStartNaming", "onAnalyzeMine"):
        assert handler in wxml, f"分享页缺少行动入口（bindtap={handler}）"

    for route in ("/pages/name/name", "/pages/analyze/analyze"):
        assert route in js, f"分享页的行动入口没有跳到 {route}"
        assert route.lstrip("/") in app_pages, f"{route} 未在 app.json 注册"


def test_share_page_declares_rebuild_params():
    """落地页必须能从参数里读出名字与出处（重建契约）。"""
    src = _read(PAGES / "share" / "share.js")
    for key in ("opt.n", "opt.c", "opt.x"):
        assert key in src, f"分享页不再读取参数 {key}，内容无法重建"


# --------------------------------------------------------------------------- #
# 5. 小程序码接口：未配置必须是 501（不是 500，也不是假图）
# --------------------------------------------------------------------------- #

def test_qrcode_service_not_configured_raises(monkeypatch):
    from app.core.config import settings
    from app.services.wx_qrcode import WxQrcodeNotConfigured, WxQrcodeService

    monkeypatch.setattr(settings, "WX_APPID", "", raising=False)
    monkeypatch.setattr(settings, "WX_SECRET", "", raising=False)

    assert WxQrcodeService.is_configured() is False

    with pytest.raises(WxQrcodeNotConfigured):
        asyncio.run(WxQrcodeService.get_entry_qrcode())


def test_qrcode_endpoint_returns_501(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "WX_APPID", "", raising=False)
    monkeypatch.setattr(settings, "WX_SECRET", "", raising=False)

    resp = TestClient(app).get("/api/v1/share/qrcode")
    assert resp.status_code == 501, (
        "未配置 AppID/Secret 时 /share/qrcode 应返回 501（前端据此显示占位印），"
        f"实际 {resp.status_code}"
    )
    assert "WX_APPID" in resp.json()["detail"], "501 的说明里没告诉运维该配哪个键"


def test_qrcode_page_is_a_registered_page(app_pages):
    from app.core.config import settings

    assert settings.WX_QRCODE_PAGE in app_pages, (
        f"WX_QRCODE_PAGE={settings.WX_QRCODE_PAGE} 不在 app.json 的 pages 里，"
        "生成出来的码会指向不存在的页面"
    )
