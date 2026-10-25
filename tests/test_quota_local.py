"""换一批配额（miniprogram/utils/quota.js）行为约束。

产品需求原话：「每次默认可以使用换一批的次数为3次，想更多换一批，需要转发或看广告。
早期可能无法接入广告，预留接口，先通过转发裂变增加次数。」

这里钉住的是**用户在页面上能感受到的规则**，不是实现细节：
1. 每天 3 次免费，第 4 次点不动（返回 exhausted，不是静默多给）；
2. 转发、看广告各最多补 3 次，补满后明确说「今天领完了」（capped），不假装成功；
3. 广告位没配时不发放次数（ad_unavailable）—— 不能先给次数再想办法；
4. 跨天自动回到满额；读写存储失败都不许把用户卡死（读失败按满额、写失败静默）；
5. 全程只落本机，不发任何请求。

额度先落本机是刻意的：没有付费墙时它只是软约束，而账号体系要先有隐私协议。
将来接后端只改 quota.js 的读写实现，页面一行不用动 —— 那时这组用例的
「规则断言」应当原样通过（只有构造存储的方式要换）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUOTA_JS = PROJECT_ROOT / "miniprogram" / "utils" / "quota.js"
API_JS = PROJECT_ROOT / "miniprogram" / "utils" / "api.js"

_NODE = shutil.which("node") or shutil.which("nodejs")
_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def _code_only(src: str) -> str:
    return _COMMENT_RE.sub("", src)

_SCRIPT = r"""
const store = {}
let requests = 0
global.wx = {
  getStorageSync(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : '' },
  setStorageSync(k, v) { store[k] = JSON.parse(JSON.stringify(v)) },
  removeStorageSync(k) { delete store[k] },
  // 配额是纯本地状态：谁调用 request 谁就越界了
  request() { requests++; throw new Error('配额不该发请求') }
}

const q = require(process.argv[1])
const api = require(process.argv[2])

const out = {}
out.initial = q.status()
out.canRefreshInitial = q.canRefresh()

// ① 免费 3 次：连点 4 下，第 4 下必须被拦
const consumes = []
for (let i = 0; i < 4; i++) consumes.push(q.consume())
out.consumes = consumes
out.afterFree = q.status()
out.canRefreshAfterFree = q.canRefresh()

// ② 广告位未配置：不许发次数
out.adUnavailable = q.grantByAd()

// ③ 转发补 3 次，第 4 次 capped
const shares = []
for (let i = 0; i < 4; i++) shares.push(q.grantByShare())
out.shares = shares
out.afterShare = q.status()

// ④ 打开广告能力后再补：同样 3 次封顶
api.REWARDED_AD_UNIT_ID = 'adunit-test'
wx.createRewardedVideoAd = function () {
  return { onError() {}, onClose() {}, show() { return Promise.resolve() }, load() { return Promise.resolve() } }
}
out.canWatchAfterEnable = q.canWatchAd()
const ads = []
for (let i = 0; i < 4; i++) ads.push(q.grantByAd())
out.ads = ads
out.afterAd = q.status()

// ⑤ 额度用尽后 remaining 不许变负数
const drain = []
for (let i = 0; i < 7; i++) drain.push(q.consume())
out.drain = drain
out.afterDrain = q.status()

// ⑥ 跨天：昨天用满 99 次，今天必须回到 3 次
store['mt_quota_v1'] = { date: '2000-01-01', used: 99, shareBonus: 3, adBonus: 3, shareCount: 3, adCount: 3 }
out.afterRollover = q.status()

// ⑦ 读失败：宁可多给一次，也不能让用户点不动
delete store['mt_quota_v1']
const realGet = wx.getStorageSync
wx.getStorageSync = function () { throw new Error('storage unreadable') }
out.onReadError = q.status()
wx.getStorageSync = realGet

// ⑧ 写失败：静默，不许抛给页面
wx.setStorageSync = function () { throw new Error('quota full') }
let writeThrew = false
try { q.consume() } catch (e) { writeThrew = true }
out.writeThrew = writeThrew

process.stdout.write(JSON.stringify({ out: out, requests: requests }))
"""


@pytest.fixture(scope="module")
def out() -> dict:
    if not _NODE:
        pytest.skip("未找到 node，跳过配额测试")
    run = subprocess.run(
        [_NODE, "-e", _SCRIPT, str(QUOTA_JS), str(API_JS)],
        capture_output=True, text=True, timeout=30,
    )
    assert run.returncode == 0, f"node 执行失败：{run.stderr}"
    return json.loads(run.stdout)


def test_daily_free_quota_is_three(out):
    """每天 3 次免费，第 4 次点不动。"""
    o = out["out"]
    assert o["initial"]["free"] == 3
    assert o["initial"]["remaining"] == 3
    assert o["initial"]["shareLeft"] == 3
    assert o["initial"]["adLeft"] == 3
    assert o["canRefreshInitial"] is True

    assert [c["ok"] for c in o["consumes"]] == [True, True, True, False]
    assert [c["remaining"] for c in o["consumes"]] == [2, 1, 0, 0]
    assert o["consumes"][3]["reason"] == "exhausted"
    assert o["canRefreshAfterFree"] is False


def test_ad_does_not_grant_when_not_configured(out):
    """广告位没配（早期常态）时不发次数，并明确告知原因。"""
    o = out["out"]
    assert o["initial"]["canWatchAd"] is False
    assert o["adUnavailable"]["ok"] is False
    assert o["adUnavailable"]["reason"] == "ad_unavailable"
    # 拒绝发放，额度不变
    assert o["adUnavailable"]["remaining"] == 0


def test_share_bonus_capped_at_three(out):
    """转发每天最多补 3 次；补满后返回 capped，而不是假装成功。"""
    o = out["out"]
    assert [s["ok"] for s in o["shares"]] == [True, True, True, False]
    assert o["shares"][3]["reason"] == "capped"
    assert o["afterShare"]["shareLeft"] == 0
    # 3 次免费已用完，补了 3 次 → 还剩 3 次
    assert o["afterShare"]["remaining"] == 3
    assert o["afterShare"]["used"] == 3


def test_ad_bonus_capped_at_three_and_separate_from_share(out):
    """广告额度与转发额度各算各的，互不挤占。"""
    o = out["out"]
    assert o["canWatchAfterEnable"] is True
    assert [a["ok"] for a in o["ads"]] == [True, True, True, False]
    assert o["ads"][3]["reason"] == "capped"
    assert o["afterAd"]["adLeft"] == 0
    assert o["afterAd"]["remaining"] == 6
    # 总额度 = 3 免费 + 3 转发 + 3 广告
    assert o["afterAd"]["used"] == 3


def test_remaining_never_goes_negative(out):
    """额度用尽后继续点，计数不加、余量不为负。"""
    o = out["out"]
    assert [d["ok"] for d in o["drain"]] == [True] * 6 + [False]
    assert o["drain"][-1]["reason"] == "exhausted"
    assert o["afterDrain"]["remaining"] == 0
    assert o["afterDrain"]["used"] == 9


def test_resets_on_new_day(out):
    """跨天回到满额（用「昨天用满 99 次」验，避免把累加当成重置）。"""
    o = out["out"]["afterRollover"]
    assert o["used"] == 0
    assert o["remaining"] == 3
    assert o["shareLeft"] == 3
    assert o["adLeft"] == 3


def test_storage_failures_never_block_the_user(out):
    """读失败按满额（宁可多给一次），写失败静默（额度不值得弹错误）。"""
    o = out["out"]
    assert o["onReadError"]["remaining"] == 3
    assert o["writeThrew"] is False


def test_no_network_call(out):
    """配额只落本机 —— 账号与隐私协议补齐之前不许上报。"""
    assert out["requests"] == 0


def test_source_has_no_identity_or_network_calls():
    """源码里不许出现身份/网络调用（守住「只落本机」这条线）。

    只扫代码，不扫注释：quota.js 的注释里写着「否则收集 openid 就是审核与
    投诉风险」——那是在解释**为什么不绑账号**，与真去拿 openid 是两回事。
    """
    code = _code_only(QUOTA_JS.read_text(encoding="utf-8"))
    for banned in ("wx.request", "wx.login", "wx.getUserInfo", "openid", "http://", "https://"):
        assert banned not in code, f"quota.js 出现了 {banned}，配额必须只落本机"
