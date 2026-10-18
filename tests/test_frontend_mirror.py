"""前端枚举镜像一致性测试（app/core/naming_options.py ⟷ miniprogram/utils/api.js）。

小程序无共享包，两边枚举靠手工同步（见 utils/api.js 顶部注释）——
这类手工镜像必然会漂移，故用测试强制约束，避免「后端加了偏好、前端筛不出来」。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.naming_options import (
    MEANING_GROUPS,
    MEANING_MAX_SELECT,
    MEANING_OPTIONS,
    SOURCE_CLASSES,
    STYLE_OPTIONS,
)
from app.services.creative_service import CHARACTER_TRAITS, NOVEL_GENRES

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_JS = PROJECT_ROOT / "miniprogram" / "utils" / "api.js"

_NODE = shutil.which("node") or shutil.which("nodejs")


def _load_frontend_enums() -> dict:
    """用 node 载入 api.js 并吐出枚举 JSON（api.js 顶层不调用 getApp，可安全 require）。"""
    if not _NODE:
        pytest.skip("未找到 node，跳过前端枚举镜像测试")
    script = (
        "const api = require(process.argv[1]);"
        "process.stdout.write(JSON.stringify({"
        "  styles: api.STYLE_OPTIONS,"
        "  meanings: api.MEANING_OPTIONS,"
        "  groups: api.MEANING_GROUPS,"
        "  map: api.SOURCE_STYLE_MAP,"
        "  sources: api.SOURCE_CLASSES,"
        "  meaningMax: api.MEANING_MAX_SELECT"
        "}));"
    )
    out = subprocess.run(
        [_NODE, "-e", script, str(API_JS)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def frontend() -> dict:
    return _load_frontend_enums()


def test_style_codes_match_backend(frontend):
    assert [s["code"] for s in frontend["styles"]] == list(STYLE_OPTIONS)


def test_meaning_codes_match_backend(frontend):
    assert [m["code"] for m in frontend["meanings"]] == list(MEANING_OPTIONS)


def test_style_names_match_backend(frontend):
    for item in frontend["styles"]:
        assert item["name"] == STYLE_OPTIONS[item["code"]]["name"], (
            f"风格 {item['code']} 名称与后端不一致"
        )


def test_style_source_preference_match_backend(frontend):
    """每个风格的 sources 必须与后端 source_preference 完全一致。"""
    for item in frontend["styles"]:
        expected = STYLE_OPTIONS[item["code"]]["source_preference"]
        assert item.get("sources") == expected, (
            f"风格 {item['code']} 的 sources 与后端 source_preference 不一致"
        )


def test_source_style_map_is_reverse_of_backend(frontend):
    """反向映射必须等于由后端 source_preference 反推的结果。"""
    expected: dict[str, list[str]] = {}
    for code, opt in STYLE_OPTIONS.items():
        for source in opt["source_preference"]:
            expected.setdefault(source, []).append(code)
    assert frontend["map"] == expected


def test_every_style_has_short_name(frontend):
    """结果页筛选条依赖 short，缺失会退化成 4 字长名而挤坏布局。"""
    for item in frontend["styles"]:
        assert item.get("short"), f"风格 {item['code']} 缺少 short 字段"


def test_schema_style_description_lists_all_codes():
    """app/schemas/schemas.py 里 style 字段的文档串必须列全 code。

    它是 OpenAPI 文档里唯一描述风格取值的地方。风格由 4 项扩到 8 项时这里曾被漏改，
    导致接口文档与实际取值不符。
    """
    src = (PROJECT_ROOT / "app" / "schemas" / "schemas.py").read_text(encoding="utf-8")
    expected = "|".join(STYLE_OPTIONS)
    assert 'description="风格偏好: %s"' % expected in src, (
        f"schemas.py 的 style 描述串未列全 code，应为 {expected}"
    )


# ── 偏好标签体系（气质 8 + 期许 14，意象不再作为用户输入）的镜像 ──

def test_select_limits_match_backend(frontend):
    """多选上限必须与后端一致，否则前端放行、后端静默截断。"""
    assert frontend["meaningMax"] == MEANING_MAX_SELECT
    assert MEANING_MAX_SELECT == 3


def test_meaning_groups_match_backend(frontend):
    """期许分组（方向）必须与后端 MEANING_GROUPS 一致：顺序、文案、组内成员归属。"""
    assert [g["code"] for g in frontend["groups"]] == [g["code"] for g in MEANING_GROUPS]
    by_code = {g["code"]: g for g in MEANING_GROUPS}
    for fg in frontend["groups"]:
        bg = by_code[fg["code"]]
        assert fg["title"] == bg["title"]
        assert fg["subtitle"] == bg["subtitle"]
    # 每个寓意都归属某个已定义的分组，且没有空分组
    valid_groups = {g["code"] for g in MEANING_GROUPS}
    for m in frontend["meanings"]:
        assert m.get("group") in valid_groups, f"寓意 {m['code']} 的 group 非法"
    for bg in MEANING_GROUPS:
        members = [m["code"] for m in frontend["meanings"] if m["group"] == bg["code"]]
        assert members, f"分组 {bg['code']}({bg['title']}) 为空"


def test_source_classes_match_backend(frontend):
    """出处类目镜像，且后端常量必须覆盖全部 source_preference 取值。"""
    assert frontend["sources"] == list(SOURCE_CLASSES)
    union: set[str] = set()
    for opt in STYLE_OPTIONS.values():
        union.update(opt["source_preference"])
    assert union <= set(SOURCE_CLASSES), (
        f"这些出处不在 SOURCE_CLASSES 里，先出处模式选不到：{sorted(union - set(SOURCE_CLASSES))}"
    )


def test_schema_source_classes_description_lists_all():
    """先出处路径的 source_classes 文档串要列全类目（与风格描述串同类约束）。"""
    src = (PROJECT_ROOT / "app" / "schemas" / "schemas.py").read_text(encoding="utf-8")
    expected = "|".join(SOURCE_CLASSES)
    assert src.count(expected) >= 2, (
        f"schemas.py 里 source_classes 描述串未列全类目，应为 {expected}"
    )


def test_schema_meaning_description_lists_all_codes():
    """同理，meanings 字段的文档串必须列全寓意 code。"""
    src = (PROJECT_ROOT / "app" / "schemas" / "schemas.py").read_text(encoding="utf-8")
    expected = "|".join(MEANING_OPTIONS)
    assert expected in src, (
        f"schemas.py 的 meanings 描述串未列全 code，应为 {expected}"
    )


# ── 创意起名（虚拟人物）：小说类型 + 性格特征枚举镜像 ──

def _load_creative_enums() -> dict:
    if not _NODE:
        pytest.skip("未找到 node，跳过前端枚举镜像测试")
    script = (
        "const api = require(process.argv[1]);"
        "process.stdout.write(JSON.stringify({"
        "  genres: api.NOVEL_GENRES,"
        "  traits: api.CHARACTER_TRAITS"
        "}));"
    )
    out = subprocess.run(
        [_NODE, "-e", script, str(API_JS)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(out.stdout)


def test_novel_genres_mirror_backend():
    frontend = _load_creative_enums()["genres"]
    assert [(g["code"], g["name"]) for g in frontend] == [
        (g["code"], g["name"]) for g in NOVEL_GENRES
    ], "api.js 的 NOVEL_GENRES 与后端不一致"


def test_character_traits_mirror_backend():
    frontend = _load_creative_enums()["traits"]
    assert [(t["code"], t["name"]) for t in frontend] == [
        (t["code"], t["name"]) for t in CHARACTER_TRAITS
    ], "api.js 的 CHARACTER_TRAITS 与后端不一致"
