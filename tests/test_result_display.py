"""结果页展示层约束：推荐值刻度、页头去重。

三件事在这里钉死：
1. **二级页不放页头图**：导航栏已有标题，再叠一张泼墨窄幅图 = 同一页两处标题（用户真机反馈「突兀」）。
2. **页内不复述导航栏标题**：去图之后若页内还写着同样四个字，重复感依旧。
3. **分数以「推荐值」呈现**：刻度由 utils/score.js 从韵味原分折算（原因见该文件顶部），
   页面只认 `item.recommend`，不再直接印 `scores.overall`。
   注意适用范围：只有**结果页**（还在挑名字）显示推荐值；
   名字本的收藏（已经选定）不显示 —— 见 `test_book_does_not_grade_saved_names`。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAGES = PROJECT_ROOT / "miniprogram" / "pages"
SCORE_JS = PROJECT_ROOT / "miniprogram" / "utils" / "score.js"

# 首页用整幅 hero 是主视觉（不是页头），不在约束内
SECONDARY = ["name", "wizard", "result", "more", "history", "creative", "naming"]

_NODE = shutil.which("node") or shutil.which("nodejs")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _visible(wxml: str) -> str:
    """去掉 WXML 注释——注释里出现标题不算「页内复述」（注释不渲染）。"""
    return re.sub(r"<!--.*?-->", "", wxml, flags=re.S)


def _nav_title(page: str) -> str:
    cfg = json.loads(_read(PAGES / page / f"{page}.json"))
    return cfg.get("navigationBarTitleText", "")


# --------------------------------------------------------------------------- #
# 1. 页头图
# --------------------------------------------------------------------------- #

def test_secondary_pages_have_no_header_image():
    for page in SECONDARY:
        wxml = _read(PAGES / page / f"{page}.wxml")
        assert "ink-band.jpg" not in wxml, (
            f"{page}.wxml 又挂上了页头图：导航栏已有标题，再加一张窄幅泼墨"
            f"就是同一页两处标题（用户已明确要求去掉）"
        )
        wxss = _read(PAGES / page / f"{page}.wxss")
        assert ".band" not in wxss, f"{page}.wxss 还留着 .band 样式（图已去掉，样式是死代码）"


def test_home_keeps_its_hero():
    wxml = _read(PAGES / "home" / "home.wxml")
    assert "home-hero" in wxml, "首页主视觉没了 —— 那是整幅 hero，不是页头图，不该一起去掉"


# --------------------------------------------------------------------------- #
# 2. 页内标题不与导航栏重复
# --------------------------------------------------------------------------- #

def test_page_heading_does_not_repeat_nav_title():
    """页内小标题（.head-title / .page-title）不得与导航栏标题逐字相同。

    只看标题元素本身，不做全文匹配 —— 「起名」是「宝宝起名」的子串，
    全文匹配会把类型卡的名字也算成复述。
    """
    heading = re.compile(
        r'<view class="(?:head-title|page-title)"[^>]*>(.*?)</view>', re.S
    )
    for page in SECONDARY:
        title = _nav_title(page)
        if not title:
            continue
        wxml = _visible(_read(PAGES / page / f"{page}.wxml"))
        for text in heading.findall(wxml):
            assert text.strip() != title, (
                f"{page}.wxml 的页内标题又是「{title}」，与导航栏一字不差 —— "
                f"去图之后页内再写一遍，重复感和有图时一样"
            )


# --------------------------------------------------------------------------- #
# 3. 推荐值
# --------------------------------------------------------------------------- #

def test_result_render_recommend_value():
    """结果页仍按「推荐值」展示（刻度见 utils/score.js）。"""
    wxml = _visible(_read(PAGES / "result" / "result.wxml"))
    assert "推荐值" in wxml, "result.wxml 的徽章少了「推荐值」前缀"
    assert "item.recommend" in wxml, "result.wxml 没在读 item.recommend"
    assert "scores.overall" not in wxml, (
        "result.wxml 仍直接印 scores.overall（原分只用于排序，展示要走 score.js）"
    )


def test_pages_compute_recommend_via_score_util():
    js = _read(PAGES / "result" / "result.js")
    assert "require('../../utils/score')" in js, (
        "result.js 没引 utils/score —— 新旧记录会各用一把尺子"
    )
    assert "score.badge(" in js, "result.js 没调用 score.badge()"


def test_book_does_not_grade_saved_names():
    """名字本的收藏**不再**折算推荐值（2026-10-24 产品评审 P1-3）。

    理由两条，都要留住：
    1. 产品原则「评分只作推荐分、不作等级分」。收藏 = 用户已经选定的名字，
       选定之后再给它打一个分数，等于在他自己的选择上又压一层评判；
    2. 收藏项只存了 `overall` 原分，而结果页显示的是折算后的推荐值 ——
       两处并排就成了一把尺子量两次、给出两个数，谁也解释不清。

    要改回「显示分数」之前，先回答上面两条怎么办。
    """
    wxml = _visible(_read(PAGES / "history" / "history.wxml"))
    js = _read(PAGES / "history" / "history.js")

    assert "推荐值" not in wxml, "history.wxml 又出现了「推荐值」"
    assert "item.recommend" not in wxml, "history.wxml 又在读 item.recommend"
    assert "score.badge" not in js, "history.js 又调用了 score.badge()"
    assert "utils/score" not in js, "history.js 又引了 utils/score"


def _run_node(expr: str) -> str:
    if not _NODE:
        pytest.skip("未找到 node，跳过 JS 刻度测试")
    script = (
        "const s = require(process.argv[1]);"
        f"process.stdout.write(String({expr}));"
    )
    out = subprocess.run(
        [_NODE, "-e", script, str(SCORE_JS)],
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0, 0),      # 无分
        (62, 73),    # 中位：62 ÷ 85 × 100 = 72.9 → 73
        (85, 99),    # 实测可达上限 → 封顶 99（不印满分）
        (90, 99),    # 超过可达上限也不溢出
    ],
)
def test_recommend_mapping(raw, expected):
    assert _run_node(f"s.recommend({raw})") == str(expected)


def test_recommend_is_monotonic():
    values = [_run_node(f"s.recommend({r})") for r in range(40, 90, 2)]
    nums = [int(v) for v in values]
    assert nums == sorted(nums), "推荐值折算必须单调 —— 否则列表排序和徽章读数会打架"


def test_recommend_tier_thresholds():
    assert _run_node("s.tier(88)") == "score-high"
    assert _run_node("s.tier(87)") == "score-mid"
    assert _run_node("s.tier(75)") == "score-mid"
    assert _run_node("s.tier(74)") == "score-low"


def test_score_util_keeps_ceiling_documented():
    js = _read(SCORE_JS)
    assert "var CEIL = 85" in js, "可达满分常量被改了 —— 改前请先跑 scripts/diag_score_scale.py"
    assert "diag_score_scale.py" in js, "刻度依据的诊断脚本没被引用，后人无从复核"
