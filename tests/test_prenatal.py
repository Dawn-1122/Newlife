"""
预产期起名引擎单测

覆盖：
- range_days=0/3/7/14 的采样天数
- 日主/喜用神分布归一化（键值之和 ≈ 1）
- stable_wuxing 非空且 <= 2
- safe_chars 无负面字黑名单
- 确定性结果字段完整
"""

import os
import sys

# 添加项目根目录到 path（兼容未设置 PYTHONPATH 的运行方式）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.core.constants import NEGATIVE_CHARS, WUXING_LIST
from app.services.prenatal_engine import PrenatalEngine


def test_sample_days_count():
    """range_days=0/3/7/14 分别采样 1/7/15/29 天"""
    engine = PrenatalEngine()
    from datetime import datetime
    due = datetime.strptime("2025-06-15", "%Y-%m-%d").date()
    for rd, expected in [(0, 1), (3, 7), (7, 15), (14, 29)]:
        dates = engine._sample_dates(due, rd)
        assert len(dates) == expected, f"range_days={rd} 应采样 {expected} 天"


def test_dist_sums_to_one():
    """分布键值之和 ≈ 1，且覆盖五行全集"""
    engine = PrenatalEngine()
    result = engine.generate("2025-06-15", 7, "male")

    dmd = result["probabilistic"]["day_master_wuxing_dist"]
    xyd = result["probabilistic"]["xiyong_wuxing_dist"]

    assert set(dmd.keys()) == set(WUXING_LIST)
    assert set(xyd.keys()) == set(WUXING_LIST)
    assert abs(sum(dmd.values()) - 1.0) < 1e-6
    assert abs(sum(xyd.values()) - 1.0) < 1e-6


def test_stable_wuxing_nonempty_le2():
    """stable_wuxing 非空且 <= 2"""
    engine = PrenatalEngine()
    for rd in [0, 3, 7, 14]:
        result = engine.generate("2025-06-15", rd, "male")
        stable = result["suggestion"]["stable_wuxing"]
        assert 0 < len(stable) <= 2, f"range_days={rd} 的 stable_wuxing 异常: {stable}"


def test_safe_chars_no_blacklist():
    """safe_chars 不包含负面字黑名单"""
    engine = PrenatalEngine()
    result = engine.generate("2025-06-15", 7, "male")
    safe_chars = result["suggestion"]["safe_chars"]
    assert safe_chars, "safe_chars 不应为空"
    for c in safe_chars:
        assert c["char"] not in NEGATIVE_CHARS
        assert c["luck"] == "吉"


def test_certain_fields_complete():
    """确定性结果字段完整"""
    engine = PrenatalEngine()
    result = engine.generate("2025-06-15", 0, "male")
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
        json={"due_date": "2025-06-15", "range_days": 7, "gender": "male"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"due_date", "range_days", "range", "certain", "probabilistic", "suggestion"}
    assert data["due_date"] == "2025-06-15"
    assert data["range_days"] == 7
    assert data["suggestion"]["stable_wuxing"]
    assert "note" in data["suggestion"]


def test_prenatal_route_invalid_range():
    """range_days 非法值返回 400"""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/prenatal",
        json={"due_date": "2025-06-15", "range_days": 5, "gender": "male"},
    )
    assert resp.status_code == 400


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
