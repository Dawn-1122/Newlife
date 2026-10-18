"""创意起名服务测试（网名昵称 / 宠物 / 商业）。

覆盖：
- 5 类 kind 都能产出结构化结果（name/tag/reason）
- 确定性：同输入同输出（刷新不跳变）
- 数量钳制、去重、关键词注入、宠物/行业差异化
- 非法 kind 抛 ValueError；HTTP 层非法 kind 422
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.creative_service import (
    CREATIVE_KINDS,
    KIND_NAMES,
    CreativeNamingService,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_JS = PROJECT_ROOT / "miniprogram" / "utils" / "api.js"


@pytest.fixture(scope="module")
def svc():
    return CreativeNamingService()


# ── 基础结构 ──

def test_all_kinds_return_names(svc):
    for kind in CREATIVE_KINDS:
        r = svc.generate(kind=kind, count=8)
        assert r["kind"] == kind
        assert r["total"] == 8
        assert len(r["names"]) == 8
        for n in r["names"]:
            assert n["name"].strip(), f"{kind} 产出了空名字"
            assert n["tag"] == KIND_NAMES[kind]
            assert n["reason"], f"{kind} 名字缺 reason"


def test_deterministic(svc):
    """同一输入必须同一结果（random 以输入为种子）。"""
    a = svc.generate(kind="game", keywords="开放世界", count=10)
    b = svc.generate(kind="game", keywords="开放世界", count=10)
    assert [n["name"] for n in a["names"]] == [n["name"] for n in b["names"]]


def test_no_duplicates_within_result(svc):
    for kind in CREATIVE_KINDS:
        r = svc.generate(kind=kind, count=20)
        names = [n["name"] for n in r["names"]]
        assert len(names) == len(set(names)), f"{kind} 结果里有重复名字"


def test_count_respected(svc):
    assert svc.generate(kind="pet", count=30)["total"] == 30
    assert svc.generate(kind="business", count=5)["total"] == 5


# ── 差异化 ──

def test_platform_injects_keywords(svc):
    """平台名称应把短关键词作基底放在最前，让用户觉得输入被听见。"""
    r = svc.generate(kind="platform", keywords="摄影师", count=6)
    assert r["names"][0]["name"].startswith("摄影师")


def test_game_does_not_inject_long_keywords(svc):
    """游戏昵称的长语义关键词（如「高校哲学讲师」）不得字面拼进名字。"""
    r = svc.generate(kind="game", keywords="高校哲学讲师 开放世界RPG", count=8)
    for n in r["names"]:
        assert "高校" not in n["name"]
        assert "讲师" not in n["name"]


def test_pet_respects_type(svc):
    cat = [n["name"] for n in svc.generate(kind="pet", pet_type="cat", count=8)["names"]]
    dog = [n["name"] for n in svc.generate(kind="pet", pet_type="dog", count=8)["names"]]
    assert cat != dog


def test_business_industry_reason(svc):
    r = svc.generate(kind="business", industry="catering", count=6)
    assert any("人气" in n["reason"] for n in r["names"])


def test_invalid_kind_raises(svc):
    with pytest.raises(ValueError):
        svc.generate(kind="nope")


# ── HTTP 层 ──

def test_creative_endpoint_ok():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post(
        "/api/v1/creative/generate",
        json={"kind": "platform", "count": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["names"]) == 5


def test_creative_endpoint_invalid_kind_422():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/api/v1/creative/generate", json={"kind": "nope"})
    assert resp.status_code == 422


# ── 前端枚举镜像 ──

def test_frontend_creative_kinds_mirror_backend():
    """api.js 的 CREATIVE_KINDS 必须与后端一致（无共享包，靠测试防漂移）。"""
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("未找到 node，跳过前端枚举镜像测试")
    script = (
        "const api = require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(api.CREATIVE_KINDS));"
    )
    out = subprocess.run(
        [node, "-e", script, str(API_JS)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    assert json.loads(out.stdout) == list(CREATIVE_KINDS)
