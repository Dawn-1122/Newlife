#!/usr/bin/env python3
"""
名堂 · 小程序 Web 预览服务

作用（五件事，不做别的）：
  1. `/`            → 吐出 tools/preview/index.html（预览外壳）
  2. `/runner.js`   → 吐出预览运行时
  3. `/__manifest`  → 把 miniprogram/ 下的 js/wxml/wxss/json **原文**打包成 JSON
  4. `/__sig`       → 源码签名（文件 mtime+size 的摘要），供外壳轮询自动重载
  5. `/mp/<path>`   → 静态映射 miniprogram/（图片等二进制资源）

设计要点：预览外壳**不复制任何页面内容**，它拿到的就是 miniprogram/ 里的原始
文件（单源，改页面不用同步改预览）。后端由页面 JS 直接请求
（后端已开 CORS allow_origins=*），所以这里不需要反向代理。

用法：
    venv/bin/python tools/preview/serve.py            # 默认 :8899
    venv/bin/python tools/preview/serve.py --port 9000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
MP_ROOT = PROJECT_ROOT / "miniprogram"

TEXT_SUFFIXES = {".js", ".wxml", ".wxss", ".json", ".wxs"}
SKIP_NAMES = {"project.private.config.json", "project.config.json"}
SKIP_DIRS = {"miniprogram_npm", "node_modules"}


def build_manifest() -> dict:
    """miniprogram/ 下所有文本文件的原文（键带 miniprogram/ 前缀）。"""
    files: dict[str, str] = {}
    for path in _iter_sources():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return {"root": "miniprogram/", "files": files}


def _iter_sources():
    for path in sorted(MP_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        if path.name in SKIP_NAMES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def source_sig() -> str:
    """源码签名。

    为什么需要：预览外壳在页面加载时把 `/__manifest` 拉进内存，之后切页面都读内存。
    改完 miniprogram 的文件、浏览器不重载，看到的就还是**旧页面** —— 表现成
    「点了没反应 / 明明改了却没生效」，非常容易误判成功能坏了。
    外壳轮询这个签名，一变就自动重载。预览器自己的 index.html / runner.js 也算在内。
    """
    h = hashlib.md5()
    for path in _iter_sources():
        st = path.stat()
        h.update(f"{path.as_posix()}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    for extra in (HERE / "index.html", HERE / "runner.js"):
        st = extra.stat()
        h.update(f"{extra.name}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    return h.hexdigest()


class Handler(SimpleHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, ctype: str | None = None) -> None:
        if not path.is_file():
            self._send(b"not found", "text/plain; charset=utf-8", 404)
            return
        data = path.read_bytes()
        guessed = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if guessed.startswith("text/") or guessed in {"application/json", "application/javascript"}:
            guessed += "; charset=utf-8"
        self._send(data, guessed)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            return self._send_file(HERE / "index.html")
        if path == "/runner.js":
            return self._send_file(HERE / "runner.js")
        if path == "/__manifest":
            payload = json.dumps(build_manifest(), ensure_ascii=False).encode("utf-8")
            return self._send(payload, "application/json; charset=utf-8")
        if path == "/__sig":
            payload = json.dumps({"sig": source_sig()}).encode("utf-8")
            return self._send(payload, "application/json; charset=utf-8")
        if path == "/favicon.ico":
            return self._send(b"", "image/x-icon", 204)
        if path.startswith("/mp/"):
            rel = path[len("/mp/"):].lstrip("/")
            target = (MP_ROOT / rel).resolve()
            if MP_ROOT.resolve() not in target.parents and target != MP_ROOT.resolve():
                return self._send(b"forbidden", "text/plain; charset=utf-8", 403)
            return self._send_file(target)

        self._send(b"not found", "text/plain; charset=utf-8", 404)

    def log_message(self, fmt: str, *args) -> None:  # 静音
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="名堂小程序 Web 预览服务")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    count = sum(1 for _ in _iter_sources())
    print(f"[preview] miniprogram 文本文件 {count} 个（每次请求实时读取，改完刷新生效）")
    print(f"[preview] 打开 http://{args.host}:{args.port}/  （后端需另起 uvicorn :8000）")

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
