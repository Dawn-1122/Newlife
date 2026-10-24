"""释名/批量对比接口测试（/analyze、/analyze/batch、收束语）。

覆盖：
- 复姓拆分（含此前内联短表漏掉的东方/夏侯，导致五格与音律整体算错）
- 批量接口与单查给出**完全相同**的分数（两条入口共用 name_analyzer）
- 非法项只跳过自己，不让整批失败
- 时辰未知时 hour_known=false（不能把内部午时当用户事实）
- 收束语不出现吉凶定论、同名结果稳定
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.core.names import is_valid_full_name, split_full_name
from app.main import app
from app.services.name_analyzer import analyze_full_name

client = TestClient(app)

# 路由统一挂在 /api/v1 下（见 app/main.py）
BASE = "/api/v1"


# ── 复姓拆分 ──

def test_split_compound_surname():
    assert split_full_name("欧阳清和") == ("欧阳", "清和")
    assert split_full_name("司马长风") == ("司马", "长风")


def test_split_surname_only_once_full():
    """「东方」两字整体作为姓名时按单姓拆，否则名会是空串。"""
    assert split_full_name("东方") == ("东", "方")


def test_split_compound_surname_beyond_inline_list():
    """东方/夏侯/长孙 等此前不在 routes 内联短表里，被拆错。"""
    assert split_full_name("东方明月") == ("东方", "明月")
    assert split_full_name("夏侯清和") == ("夏侯", "清和")
    assert split_full_name("长孙无忌") == ("长孙", "无忌")


def test_single_surname():
    assert split_full_name("林清野") == ("林", "清野")


# ── 姓名合法性 ──

def test_invalid_full_name_rejects_latin():
    ok, reason = is_valid_full_name("Alex")
    assert not ok and "汉字" in reason


def test_full_name_allows_middle_dot():
    """少数民族姓名里的间隔号是合法的。"""
    ok, _ = is_valid_full_name("阿依古丽·买")
    assert ok


def test_full_name_length_limits():
    assert not is_valid_full_name("李")[0]
    assert not is_valid_full_name("李" * 11)[0]


# ── 单查 / 批量一致性 ──

def test_analyze_returns_verdict_and_hour_flag():
    r = client.post(BASE + "/analyze", json={"full_name": "林清野"})
    assert r.status_code == 200
    body = r.json()
    assert body["surname"] == "林"
    assert body["given_name"] == "清野"
    assert body["verdict"]
    # 没给时辰 → 不能声称时辰已知
    assert body["hour_known"] is False


def test_analyze_hour_known_when_given():
    body = client.post(BASE + "/analyze", json={
        "full_name": "林清野", "year": 1990, "month": 5, "day": 18, "hour": 9,
    }).json()
    assert body["hour_known"] is True
    assert body["bazi_match"]["bazi"]["four_pillars"]["hour"]


def test_batch_matches_single_analyze():
    """同一个名字，批量给出的分数与单查一字不差（否则用户会看到两个版本）。"""
    names = ["林清野", "顾素秋"]
    batch = client.post(BASE + "/analyze/batch", json={"names": names}).json()

    assert [it["full_name"] for it in batch["items"]] == names
    for item in batch["items"]:
        single = client.post(BASE + "/analyze", json={"full_name": item["full_name"]}).json()
        assert item["phonetics"] == single["phonetics"]
        assert item["wuge"] == single["wuge"]
        assert item["verdict"] == single["verdict"]


def test_batch_dedupes_and_rejects_partially():
    r = client.post(BASE + "/analyze/batch", json={"names": ["林清野", "林清野", "A1", "顾素秋"]})
    assert r.status_code == 200
    body = r.json()

    assert [it["full_name"] for it in body["items"]] == ["林清野", "顾素秋"]
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["name"] == "A1"


def test_batch_limit_five_names():
    """超过 5 个由 schema 挡住，避免一次算太多拖慢接口。"""
    r = client.post(BASE + "/analyze/batch", json={"names": ["林清野"] * 6})
    assert r.status_code == 422


def test_batch_empty_list_rejected():
    r = client.post(BASE + "/analyze/batch", json={"names": []})
    assert r.status_code == 422


# ── 收束语的产品底线 ──

def test_verdict_has_no_luck_wording():
    """收束语不许出现吉/凶定论（产品底线，见 wuge._describe 注释）。"""
    for name in ["林清野", "顾素秋", "欧阳清和", "张章张"]:
        verdict = analyze_full_name(name)["verdict"]
        for banned in ("大吉", "吉", "凶", "必定", "注定", "一生"):
            assert banned not in verdict, f"{name} 的收束语出现了「{banned}」：{verdict}"


def test_verdict_is_stable():
    """同一个名字两次释名给同一段话 —— 收束句按姓名稳定取。"""
    assert analyze_full_name("林清野")["verdict"] == analyze_full_name("林清野")["verdict"]


def test_verdict_follows_data_not_template():
    """不同用字/音律必须给出不同的话，不能是一段套话。"""
    a = analyze_full_name("林清野")["verdict"]
    b = analyze_full_name("张章张")["verdict"]
    assert a != b
