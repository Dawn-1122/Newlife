"""随机摆盘（抽卡感）测试。

产品需求原话：「在可推荐名字中随机显示，不用按推荐分从高到低排序。
可以类似抽卡，有可能抽出更满意的名字。」

实现上有一条**必须守住**的边界：只改摆盘顺序，不改选谁。
门槛（五格/音律硬淘汰）、分层配额 8:2、偏好硬分流、softmax 权重、带宽窗口
全都不动 —— 所以打乱不会让本该被淘汰的弱名漏进来，只是不再按分数排队。

这里钉住四件事：
1. shuffle=False 时严格按韵味降序（脚本 / 评测要可复现的榜单语义）；
2. shuffle=True 时顺序确实被打乱（不是「看起来乱」）；
3. 打乱是**纯置换**：同一随机种子下选中集合不变，只有顺序变；
4. 重复同一输入，首位名字会变（抽卡感成立，否则用户翻两批就发现规律）。
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.schemas import NamingRequest
from app.services.naming_engine import NamingEngine

client = TestClient(app)
BASE = "/api/v1"

# 一份固定输入：有出生时间才会走八字，样本更接近真实请求
_BASE_KW = dict(
    surname="林", gender="male",
    year=1990, month=5, day=20, hour=10,
    max_results=6,
)


def _gen(shuffle: bool, seed: int = 3) -> list[dict]:
    """同一 seed 生成一批名字，用于把「随机」变成可断言的固定样本。"""
    random.seed(seed)
    out = NamingEngine().generate_names(shuffle=shuffle, **_BASE_KW)
    return out["names"]


def _yunwei(item: dict) -> float:
    return item["scores"]["yunwei"]


def test_plain_order_is_descending():
    """shuffle=False：严格非递增，榜单语义（评测脚本依赖这个）。"""
    scores = [_yunwei(n) for n in _gen(shuffle=False)]
    assert len(scores) >= 2, "样本不足，后面的排序断言没有意义"
    assert scores == sorted(scores, reverse=True), f"未按韵味降序：{scores}"


def test_shuffle_breaks_score_order():
    """shuffle=True：至少出现一次「后面的比前面的分高」，即真的换过位。"""
    # 单个 seed 可能恰好抽出接近原序，多看几个 seed 再下结论
    inversions = 0
    for seed in (1, 2, 3, 4, 5):
        scores = [_yunwei(n) for n in _gen(shuffle=True, seed=seed)]
        if scores != sorted(scores, reverse=True):
            inversions += 1
    assert inversions >= 4, f"5 个 seed 里只有 {inversions} 个真的打乱了，shuffle 可能没接线"


def _pool(seed: int = 7) -> list[dict]:
    """造一个比 k 大的候选池，用于直接驱动 _stratified_sample 的主分支。"""
    random.seed(seed)
    return NamingEngine().generate_names(shuffle=False, **dict(_BASE_KW, max_results=30))["names"]


def test_shuffle_only_permutes_the_picked_set():
    """同一随机种子下，打乱前后「进榜的名字」一个不多一个不少，只有顺序不同。

    这正是「只改摆盘、不改选谁」的证明：`_stratified_sample` 里 shuffle 是
    **最后一步**，它之前的所有随机消耗（带宽窗口取整、softmax 抽样）在两次调用中
    完全一致，所以选中集合必然相同。

    ⚠️ 不要改成在 `generate_names` 层比较两次真实运行的集合 —— 引擎内部还有
    其他 `random.shuffle`（分层前的分组、合并去重），多消耗一次随机数就会
    让后续抽样整体漂移，断言会随机失败。要证「纯置换」只能在这里证。
    """
    e = NamingEngine()
    pool = _pool()

    random.seed(21)
    plain = [n["full_name"] for n in e._stratified_sample(pool, 6, shuffle=False)]
    random.seed(21)
    shuffled = [n["full_name"] for n in e._stratified_sample(pool, 6, shuffle=True)]

    assert sorted(shuffled) == sorted(plain), "打乱改变了选中的名字集合"
    assert shuffled != plain, "shuffle=True 却没换过位"


def test_repeated_runs_vary_the_lead_name():
    """抽卡感：同一份输入反复生成，首位名字会变。

    这条不做统计显著性断言，只验证「不是每次都同一个」——
    若某天把 softmax 改成取 top-k，首位会稳定不变，这里会先失败。
    """
    leads = set()
    for _ in range(8):
        batch = NamingEngine().generate_names(shuffle=True, **_BASE_KW)["names"]
        leads.add(batch[0]["full_name"])
    assert len(leads) >= 2, f"8 次生成首位始终是 {leads}，抽卡感不成立"


# ── 请求层：默认值与透传 ──

def test_schema_defaults_to_shuffle():
    """接口默认就是抽卡式（shuffle=True），前端不必显式传。"""
    req = NamingRequest(surname="林")
    assert req.shuffle is True


def test_route_accepts_batch_size_six():
    """前端每批 6 个：max_results=6 要能正常取到 6 条。"""
    body = dict(_BASE_KW, max_results=6, shuffle=False)
    res = client.post(f"{BASE}/generate", json=body)
    assert res.status_code == 200, res.text
    assert len(res.json()["names"]) == 6


def test_route_passes_shuffle_through():
    """shuffle=False 必须真的传到引擎 —— 否则降级/脚本拿不到可复现榜单。"""
    body = dict(_BASE_KW, shuffle=False)
    res = client.post(f"{BASE}/generate", json=body)
    assert res.status_code == 200, res.text
    scores = [n["scores"]["yunwei"] for n in res.json()["names"]]
    assert scores == sorted(scores, reverse=True), f"路由没透传 shuffle：{scores}"
