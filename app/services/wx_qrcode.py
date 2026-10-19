"""
微信小程序码（分享页用）

为什么要走服务端而不是前端直接拿：
    `cgi-bin/token` 需要 AppSecret，一旦下发到小程序包就等于公开泄露。
    故由后端取 token 并缓存，前端只拿图片。

当前阶段（未提审）的现实约束：
    1. 没有 AppID/AppSecret → 直接抛 `WxQrcodeNotConfigured`，路由转 501，
       前端显示占位印，不报错、不白屏。
    2. `wxa/getwxacodeunlimit` 默认校验 page 是否已发布；开发期页面未发布，
       故显式传 check_path=False。
    3. scene 只允许 32 个字符且**不支持中文**，所以码指向固定入口
       （pages/name/name?scene=entry），而不是"某个具体名字"。
       要让码直接打开某个名字，得先有短链/快照服务，属于 P1。
"""

from __future__ import annotations

import time
from typing import Optional

import httpx

from app.core.config import settings

WX_API_BASE = "https://api.weixin.qq.com"

# access_token 官方有效期 7200s，留 200s 余量避免临界失效
TOKEN_TTL_SECONDS = 7000

# 小程序码尺寸（微信要求 280~1280）
DEFAULT_QRCODE_WIDTH = 430


class WxQrcodeError(RuntimeError):
    """微信接口调用失败（网络、鉴权、配额等）。"""


class WxQrcodeNotConfigured(WxQrcodeError):
    """未配置 AppID/AppSecret。"""


class WxQrcodeService:
    """小程序码服务（进程内缓存 access_token）。"""

    _token: Optional[str] = None
    _token_expire_at: float = 0.0

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.WX_APPID and settings.WX_SECRET)

    @classmethod
    def _cached_token(cls) -> Optional[str]:
        if cls._token and time.monotonic() < cls._token_expire_at:
            return cls._token
        return None

    @classmethod
    async def _get_token(cls, client: httpx.AsyncClient) -> str:
        cached = cls._cached_token()
        if cached:
            return cached

        resp = await client.get(
            f"{WX_API_BASE}/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": settings.WX_APPID,
                "secret": settings.WX_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        token = data.get("access_token")
        if not token:
            # 微信的失败响应长这样：{"errcode":40013,"errmsg":"invalid appid"}
            raise WxQrcodeError(
                f"获取 access_token 失败：{data.get('errcode')} {data.get('errmsg', '')}".strip()
            )

        expires_in = int(data.get("expires_in") or 7200)
        cls._token = token
        cls._token_expire_at = time.monotonic() + min(expires_in - 200, TOKEN_TTL_SECONDS)
        return token

    @classmethod
    async def get_entry_qrcode(cls, width: int = DEFAULT_QRCODE_WIDTH) -> bytes:
        """取指向起名入口的小程序码（PNG 字节）。"""
        if not cls.is_configured():
            raise WxQrcodeNotConfigured(
                "小程序码未启用：需要在 .env 配置 WX_APPID / WX_SECRET"
            )

        width = max(280, min(int(width), 1280))

        async with httpx.AsyncClient(timeout=10.0) as client:
            token = await cls._get_token(client)
            resp = await client.post(
                f"{WX_API_BASE}/wxa/getwxacodeunlimit",
                params={"access_token": token},
                json={
                    "scene": settings.WX_QRCODE_SCENE,
                    "page": settings.WX_QRCODE_PAGE,
                    "width": width,
                    "check_path": False,
                    # 透明底要配 jpg 以外的格式；走默认 png，白底更耐看
                    "auto_color": False,
                },
            )
            resp.raise_for_status()

            content = resp.content
            content_type = resp.headers.get("content-type", "")

            # 成功返回 PNG 二进制；失败返回 JSON —— 靠 content-type 分辨
            if "application/json" in content_type:
                try:
                    data = resp.json()
                except ValueError as exc:  # pragma: no cover - 极端异常
                    raise WxQrcodeError("小程序码接口返回了无法解析的响应") from exc
                raise WxQrcodeError(
                    f"生成小程序码失败：{data.get('errcode')} {data.get('errmsg', '')}".strip()
                )

            if not content:
                raise WxQrcodeError("小程序码接口返回空内容")

            return content
