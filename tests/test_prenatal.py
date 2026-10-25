"""
预产期历法参考引擎单测

覆盖：
- range_days=0/3/7/14 的采样天数
- 日柱天干五行分布归一化（键值之和 ≈ 1、覆盖五行全集、分母是采样天数）
- 确定性历法字段完整
- 路由结构（且**不含**任何建议字段）
- 页面把分布转成百分比时，五项加起来必须正好 100

合规守卫见 test_response_has_no_advice_fields —— 这条测试的存在意义是：
将来谁想「顺手把喜用神加回来」，会先撞到它。
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

# 添加项目根目录到 path（兼容未设置 PYTHONPATH 的运行方式）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.core.constants import WUXING_LIST
from app.services.prenatal_engine import PrenatalEngine

PRENATAL_PAGE_JS = os.path.join(
    PROJECT_ROOT, "miniprogram", "pages", "prenatal-result", "prenatal-result.js"
)
_NODE = shutil.which("node") or shutil.which("nodejs")


# 响应里一旦出现这些键，说明「建议 / 喜用神」能力又回来了
FORBIDDEN_KEYS = {"suggestion", "xiyong_wuxing_dist", "stable_wuxing", "safe_chars", "note"}
# 文案里出现这些词，说明又在解释或预测
FORBIDDEN_WORDS = ("喜用", "忌神", "身强", "身弱", "建议", "宜用", "补益")


def _all_keys(node) -> set:
    """递归收集 JSON 里出现过的所有键名"""
    keys = set()
    if isinstance(node, dict):
        for k, v in node.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(node, list):
        for item in node:
            keys |= _all_keys(item)
    return keys


def _all_text(node) -> str:
    """递归收集 JSON 里所有字符串值（拼成一串，方便扫敏感词）"""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return " ".join(_all_text(v) for v in node.values())
    if isinstance(node, list):
        return " ".join(_all_text(v) for v in node)
    return ""


def test_sample_days_count():
    """range_days=0/3/7/14 分别采样 1/7/15/29 天"""
    engine = PrenatalEngine()
    due = datetime.strptime("2025-06-15", "%Y-%m-%d").date()
    for rd, expected in [(0, 1), (3, 7), (7, 15), (14, 29)]:
        dates = engine._sample_dates(due, rd)
        assert len(dates) == expected, f"range_days={rd} 应采样 {expected} 天"


def test_day_master_dist_sums_to_one():
    """分布键值之和 ≈ 1，且覆盖五行全集"""
    engine = PrenatalEngine()
    result = engine.generate("2025-06-15", 7)

    dmd = result["probabilistic"]["day_master_wuxing_dist"]

    assert set(dmd.keys()) == set(WUXING_LIST)
    assert abs(sum(dmd.values()) - 1.0) < 1e-6


def test_single_day_dist_is_one_hot():
    """range_days=0 时只有一天，分布必然是「一项 100%、其余 0%」"""
    engine = PrenatalEngine()
    result = engine.generate("2025-06-15", 0)

    dmd = result["probabilistic"]["day_master_wuxing_dist"]

    ones = [w for w, p in dmd.items() if abs(p - 1.0) < 1e-9]
    zeros = [w for w, p in dmd.items() if abs(p) < 1e-9]
    assert len(ones) == 1, f"应恰好一种五行占 100%，实际 {ones}"
    assert len(zeros) == 4


def test_dist_denominator_is_sampled_days():
    """占比的分母是采样天数：任何一项都必须是 1/天数 的整数倍"""
    engine = PrenatalEngine()
    for rd in [3, 7, 14]:
        days = rd * 2 + 1
        dmd = engine.generate("2025-06-15", rd)["probabilistic"]["day_master_wuxing_dist"]
        for w, p in dmd.items():
            count = p * days
            assert abs(count - round(count)) < 1e-6, (
                f"range_days={rd} 的 {w} 占比 {p} 不是 1/{days} 的整数倍，分母错了"
            )


def test_certain_fields_complete():
    """确定性历法字段完整"""
    engine = PrenatalEngine()
    result = engine.generate("2025-06-15", 0)
    certain = result["certain"]
    assert certain["shengxiao"]
    assert certain["month_ganzhi"]
    assert certain["month_wuxing"]
    assert result["range"]["start"] == "2025-06-15"
    assert result["range"]["end"] == "2025-06-15"


def test_prenatal_route():
    """POST /api/v1/prenatal 返回结构完整"""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/prenatal",
        json={"due_date": "2025-06-15", "range_days": 7},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {
        "due_date", "range_days", "range", "certain", "probabilistic"
    }
    assert data["due_date"] == "2025-06-15"
    assert data["range_days"] == 7
    assert data["probabilistic"]["day_master_wuxing_dist"]


def test_prenatal_route_ignores_legacy_fields():
    """前端还在传 gender/style/meanings 也不会报错，且不会长出建议字段"""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/prenatal",
        json={
            "due_date": "2025-06-15",
            "range_days": 3,
            "gender": "female",
            "style": "elegant",
            "meanings": ["wisdom"],
            "avoid_chars": ["伟"],
        },
    )
    assert resp.status_code == 200
    assert "suggestion" not in resp.json()


def test_response_has_no_advice_fields():
    """
    合规守卫：响应里不得出现「喜用神分布 / 稳定五行 / 候选字 / 结论文案」。

    不预测命理、不提供建议 —— 给未出生的孩子推断喜用五行本身就是预测命理。
    """
    client = TestClient(app)
    resp = client.post(
        "/api/v1/prenatal",
        json={"due_date": "2025-06-15", "range_days": 14},
    )
    assert resp.status_code == 200
    data = resp.json()

    keys = _all_keys(data)
    hit = keys & FORBIDDEN_KEYS
    assert not hit, f"响应里出现了不该有的字段：{hit}"

    text = _all_text(data)
    bad = [w for w in FORBIDDEN_WORDS if w in text]
    assert not bad, f"响应文案里出现了判断性用语：{bad}"


def test_prenatal_route_invalid_range():
    """range_days 非法值返回 400"""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/prenatal",
        json={"due_date": "2025-06-15", "range_days": 5},
    )
    assert resp.status_code == 400


def test_prenatal_route_invalid_date():
    """预产期格式非法返回 400"""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/prenatal",
        json={"due_date": "2025/06/15", "range_days": 7},
    )
    assert resp.status_code == 400


_NODE_SCRIPT = r"""
const pagePath = process.argv[1]

global.wx = { navigateBack() {}, showToast() {} }
let cfg = null
global.Page = function (c) { cfg = c }
const appState = { globalData: { prenatalResult: null } }
global.getApp = function () { return appState }

require(pagePath)

function load(dist) {
  appState.globalData.prenatalResult = {
    due_date: '2025-06-15',
    range_days: 7,
    range: { start: '2025-06-08', end: '2025-06-22' },
    certain: { shengxiao: '蛇', month_ganzhi: '壬午', month_wuxing: '火' },
    probabilistic: { day_master_wuxing_dist: dist }
  }
  const page = Object.assign({}, cfg)
  page.data = JSON.parse(JSON.stringify(cfg.data))
  page.setData = function (d) { this.data = Object.assign({}, this.data, d) }
  page.onLoad()
  return page.data
}

const out = {}
// 15 天，计数 [1,2,3,4,5]：各项都是 6.66…% 的倍数，逐项四舍五入会得到 98 或 102
out.uneven = load({ '金': 1 / 15, '木': 2 / 15, '水': 3 / 15, '火': 4 / 15, '土': 5 / 15 }).dayMasterDist
// 没有任何计数（接口降级 / 字段缺失）不许凭空长出百分比
out.empty = load({}).dayMasterDist
// 单日：一项 100%，其余 0
out.single = load({ '金': 0, '木': 1, '水': 0, '火': 0, '土': 0 }).dayMasterDist
// 页面自己存了哪些键（用来断言「建议类数据」没有回到页面）
out.pageKeys = Object.keys(cfg.data)
out.distNames = out.uneven.map(function (r) { return r.name })
console.log(JSON.stringify(out))
"""


def _run_page():
    """在 node 里载入孕期结果页，跑一遍 onLoad，取回渲染数据"""
    proc = subprocess.run(
        [_NODE, "-e", _NODE_SCRIPT, PRENATAL_PAGE_JS],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"node 执行失败：{proc.stderr}"
    return json.loads(proc.stdout.strip())


def _sum_of(rows):
    return sum(r["percent"] for r in rows)


@pytest.mark.skipif(_NODE is None, reason="需要 node 才能载入页面 js")
def test_page_percents_always_sum_to_100():
    """百分比必须正好加到 100 —— 这一页唯一的内容就是这组统计"""
    out = _run_page()
    assert _sum_of(out["uneven"]) == 100, out["uneven"]
    assert out["distNames"] == list(WUXING_LIST), "五行顺序与后端常量不一致"
    for r in out["uneven"]:
        assert r["percent"] >= 0


@pytest.mark.skipif(_NODE is None, reason="需要 node 才能载入页面 js")
def test_page_percents_empty_and_single():
    """没有数据时不许凭空给 1%；只有一天时那一种五行必须是 100%"""
    out = _run_page()
    assert _sum_of(out["empty"]) == 0
    assert all(r["percent"] == 0 for r in out["empty"])
    assert _sum_of(out["single"]) == 100
    by_name = {r["name"]: r["percent"] for r in out["single"]}
    assert by_name["木"] == 100
    assert sum(1 for v in by_name.values() if v == 100) == 1


@pytest.mark.skipif(_NODE is None, reason="需要 node 才能载入页面 js")
def test_page_data_has_no_advice_field():
    """页面 data 里不得出现「喜用 / 建议」类字段（合规口径的页面侧守卫）"""
    out = _run_page()
    keys = set(out["pageKeys"])
    assert keys == {"result", "dayMasterDist", "totalDays"}, (
        f"孕期结果页的 data 应只剩统计字段，实际：{sorted(keys)}"
    )


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
