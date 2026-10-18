"""创意起名服务测试（网名昵称 / 宠物 / 商业 / 虚拟人物）。

覆盖：
- 5 类 kind 都能产出结构化结果（name/tag/reason）
- 确定性：同输入同输出（刷新不跳变）
- 数量钳制、去重、关键词注入、宠物/行业差异化
- 虚拟人物：类型/性格驱动 + LLM 自定义描述（未配置降级本地）
- 非法 kind 抛 ValueError；HTTP 层非法 kind 422
"""

import asyncio
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


# ── 平台名称：平台基因分库 ──

def test_platform_type_distinguishes_names(svc):
    """不同平台应产出不同风格（小红书 ≠ 知乎）。"""
    xhs = [n["name"] for n in svc.generate(kind="platform", platform_type="xiaohongshu", count=8)["names"]]
    zh = [n["name"] for n in svc.generate(kind="platform", platform_type="zhihu", count=8)["names"]]
    assert xhs != zh


def test_platform_type_reason_names_platform(svc):
    """平台 reason 应带平台名。"""
    r = svc.generate(kind="platform", platform_type="zhihu", count=5)
    assert any("知乎" in n["reason"] for n in r["names"])


def test_platform_type_deterministic(svc):
    """同平台同输入必须同输出。"""
    a = svc.generate(kind="platform", platform_type="douyin", count=10)
    b = svc.generate(kind="platform", platform_type="douyin", count=10)
    assert [n["name"] for n in a["names"]] == [n["name"] for n in b["names"]]


# ── 游戏昵称：游戏类型分库 + 职业关键词注入 ──

def test_game_type_distinguishes_names(svc):
    """不同游戏类型应产出不同风格（仙侠奇幻 ≠ 科幻）。"""
    fantasy = [n["name"] for n in svc.generate(kind="game", game_type="fantasy", count=8)["names"]]
    scifi = [n["name"] for n in svc.generate(kind="game", game_type="scifi", count=8)["names"]]
    assert fantasy != scifi


def test_game_injects_career_keywords(svc):
    """游戏昵称应把 2 字职业关键词 + 游戏机制语汇组合（职业×机制双轨）。"""
    r = svc.generate(kind="game", keywords="温控", game_type="scifi", count=8)
    assert any(n["name"].startswith("温控") for n in r["names"])


def test_game_type_reason_names_type(svc):
    """游戏 reason 应带游戏类型名。"""
    r = svc.generate(kind="game", game_type="tactical", count=5)
    assert any("硬核战术" in n["reason"] for n in r["names"])


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


# ── 虚拟人物：类型/性格驱动 ──

def test_role_genre_trait_drives_names(svc):
    """类型+性格驱动的虚拟人物起名：应产三字「姓+核+字」名，reason 带类型/性格名。"""
    r = svc.generate(kind="role", genre="xianxia", trait="qingleng", count=12)
    names = [n["name"] for n in r["names"]]
    assert any(len(n) == 3 for n in names), f"缺少三字名: {names}"
    assert any("仙侠" in n["reason"] and "清冷" in n["reason"] for n in r["names"])


def test_role_genre_only_dedup(svc):
    r = svc.generate(kind="role", genre="moshi", count=20)
    names = [n["name"] for n in r["names"]]
    assert len(names) == len(set(names)), "类型驱动结果出现重复名字"


def test_role_gender_distinguishes_names(svc):
    """性别应参与角色起名：男/女产出不同。"""
    male = [n["name"] for n in svc.generate(
        kind="role", genre="xianxia", trait="qingleng", gender="male", count=12
    )["names"]]
    female = [n["name"] for n in svc.generate(
        kind="role", genre="xianxia", trait="qingleng", gender="female", count=12
    )["names"]]
    assert male != female, "男/女产出完全相同，性别未参与区分"


def test_role_gender_chars_in_names(svc):
    """指定性别时，产出名应含对应性别气质字。"""
    from app.services.creative_service import CREATIVE_BANKS
    male_chars = set(CREATIVE_BANKS["role_male_chars"])
    female_chars = set(CREATIVE_BANKS["role_female_chars"])
    male = svc.generate(kind="role", genre="xianxia", trait="qingleng", gender="male", count=20)
    female = svc.generate(kind="role", genre="xianxia", trait="qingleng", gender="female", count=20)
    assert any(any(c in male_chars for c in n["name"]) for n in male["names"]), \
        "男名未含男性气质字"
    assert any(any(c in female_chars for c in n["name"]) for n in female["names"]), \
        "女名未含女性气质字"


def test_role_gender_deterministic(svc):
    """同性别 + 同输入必须同输出（性别参与种子，不破坏确定性）。"""
    a = svc.generate(kind="role", genre="kehuan", gender="female", count=10)
    b = svc.generate(kind="role", genre="kehuan", gender="female", count=10)
    assert [n["name"] for n in a["names"]] == [n["name"] for n in b["names"]]


def test_role_llm_passes_gender(svc, monkeypatch):
    """LLM 路径也应把性别传进 prompt（约束里带「男/女」）。"""
    from app.services import creative_service as cs
    monkeypatch.setattr(cs.settings, "LLM_API_KEY", "sk-test")
    captured = {}

    async def fake_chat(self, messages, temperature, max_tokens, json_mode):
        captured["prompt"] = messages[-1]["content"]
        return {"names": [{"name": "沈云衡", "reason": "仙侠男"}]}
    monkeypatch.setattr(cs.LLMService, "chat", fake_chat)

    asyncio.run(svc.generate_llm(
        description="修仙剑客", genre="xianxia", gender="male", count=3
    ))
    assert "角色性别：男" in captured["prompt"]


# ── 虚拟人物：LLM 自定义描述（配置驱动） ──

def test_llm_fallback_when_unconfigured(svc, monkeypatch):
    """LLM 未配置时降级本地词库，source=local 且附 fallback_note。"""
    from app.services import creative_service as cs
    monkeypatch.setattr(cs.settings, "LLM_API_KEY", "")
    r = asyncio.run(svc.generate_llm(
        description="修仙界落难女剑仙", genre="xianxia", trait="qingleng", count=8
    ))
    assert r["source"] == "local"
    assert r["total"] == 8
    assert r["provider"] is None and r["model"] is None
    assert "本地词库" in (r["fallback_note"] or "")
    for n in r["names"]:
        assert n["name"].strip() and n["tag"] == KIND_NAMES["role"] and n["reason"]


def test_llm_configured_parses_names(svc, monkeypatch):
    """LLM 配置后调 chat（json_mode），正常解析为结构化名字。"""
    from app.services import creative_service as cs
    monkeypatch.setattr(cs.settings, "LLM_API_KEY", "sk-test")

    async def fake_chat(self, messages, temperature, max_tokens, json_mode):
        assert json_mode is True
        return {"names": [
            {"name": "沈云白", "reason": "仙侠清冷"},
            {"name": "顾听澜", "reason": "温润如玉"},
        ]}
    monkeypatch.setattr(cs.LLMService, "chat", fake_chat)

    r = asyncio.run(svc.generate_llm(
        description="修仙界女剑仙", genre="xianxia", trait="qingleng", count=5
    ))
    assert r["source"] == "llm"
    assert [n["name"] for n in r["names"]] == ["沈云白", "顾听澜"]
    assert r["fallback_note"] is None


def test_llm_empty_result_falls_back(svc, monkeypatch):
    """LLM 返回空/垃圾时降级本地词库。"""
    from app.services import creative_service as cs
    monkeypatch.setattr(cs.settings, "LLM_API_KEY", "sk-test")

    async def bad_chat(self, messages, temperature, max_tokens, json_mode):
        return {"names": []}
    monkeypatch.setattr(cs.LLMService, "chat", bad_chat)

    r = asyncio.run(svc.generate_llm(description="修仙", genre="xianxia", count=6))
    assert r["source"] == "local"
    assert r["total"] == 6


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


def test_creative_llm_endpoint_ok(monkeypatch):
    """/creative/llm 未配置 LLM 时应 200 + source=local 降级。"""
    from app.services import creative_service as cs
    monkeypatch.setattr(cs.settings, "LLM_API_KEY", "")
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/api/v1/creative/llm", json={
        "description": "赛博朋克义体医生", "genre": "kehuan", "trait": "chenwen", "count": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "local"
    assert data["total"] == 5
    assert len(data["names"]) == 5


def test_creative_llm_endpoint_missing_description_422():
    """/creative/llm 缺 description 时 422。"""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/api/v1/creative/llm", json={"count": 5})
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
