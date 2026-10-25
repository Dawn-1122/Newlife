"""起名批次额度（miniprogram/utils/quota.js）行为约束。

口径（2026-10-25 定）：**一个池子，每天 9 批**，起名与换一批各扣 1；
转发一次 +3 批（每天最多领 2 次）、看广告一次 +3 批（同）。

早先是「每次起名送 3 次换一批」，两个毛病：文案只能说「今天的换一批用完了」
却又不跟这一天绑定；而且回上一页重新提交就又是一批新的，额度拦不住人。

这里钉住的是**用户在页面上能感受到的规则**，不是实现细节：
1. 每天 9 批，第 10 次扣不动（返回 exhausted，不是静默多给）；
2. 转发 / 广告各最多领 2 次，领满后明确说「今天领完了」（capped），不假装成功；
3. 广告位没配时不发放（ad_unavailable）—— 不能先给批次再想办法；
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

// ① 免费 9 批：连点 10 下，第 10 下必须被拦
const consumes = []
for (let i = 0; i < 10; i++) consumes.push(q.consume())
out.consumes = consumes
out.afterFree = q.status()
out.canRefreshAfterFree = q.canRefresh()

// ② 广告位未配置：不许发批次
out.adUnavailable = q.grantByAd()
out.canEarnBeforeAd = q.canEarnByAd()

// ③ 转发每次 +3 批、每天最多领 2 次，第 3 次 capped
const shares = []
for (let i = 0; i < 3; i++) shares.push(q.grantByShare())
out.shares = shares
out.afterShare = q.status()

// ④ 打开广告能力后再补：同样 3 次封顶
api.REWARDED_AD_UNIT_ID = 'adunit-test'
wx.createRewardedVideoAd = function () {
  return { onError() {}, onClose() {}, show() { return Promise.resolve() }, load() { return Promise.resolve() } }
}
out.canWatchAfterEnable = q.canWatchAd()
out.canEarnAfterEnable = q.canEarnByAd()
const ads = []
for (let i = 0; i < 3; i++) ads.push(q.grantByAd())
out.ads = ads
out.afterAd = q.status()
// 广告额度领完之后，页面必须能在放视频之前就拦住（别让人白看 30 秒）
out.canEarnAfterAdUsedUp = q.canEarnByAd()

// ⑤ 额度用尽后 remaining 不许变负数
const drain = []
for (let i = 0; i < 13; i++) drain.push(q.consume())
out.drain = drain
out.afterDrain = q.status()

// ⑥ 跨天：昨天用满 99 批，今天必须回到 9 批
store['mt_quota_v1'] = { date: '2000-01-01', used: 99, shareBonus: 6, adBonus: 6, shareCount: 2, adCount: 2 }
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


def test_daily_free_quota_is_nine(out):
    """每天 9 批（起名与换一批共用一个池），第 10 次扣不动。"""
    o = out["out"]
    assert o["initial"]["free"] == 9
    assert o["initial"]["remaining"] == 9
    assert o["initial"]["shareLeft"] == 2
    assert o["initial"]["adLeft"] == 2
    assert o["initial"]["shareBonus"] == 3
    assert o["canRefreshInitial"] is True

    assert [c["ok"] for c in o["consumes"]] == [True] * 9 + [False]
    assert [c["remaining"] for c in o["consumes"]] == list(range(8, -1, -1)) + [0]
    assert o["consumes"][-1]["reason"] == "exhausted"
    assert o["canRefreshAfterFree"] is False


def test_ad_does_not_grant_when_not_configured(out):
    """广告位没配（早期常态）时不发次数，并明确告知原因。"""
    o = out["out"]
    assert o["initial"]["canWatchAd"] is False
    assert o["adUnavailable"]["ok"] is False
    assert o["adUnavailable"]["reason"] == "ad_unavailable"
    # 拒绝发放，额度不变
    assert o["adUnavailable"]["remaining"] == 0
    # 广告放不出来时，也不该让页面走到「播视频」这一步
    assert o["canEarnBeforeAd"] is False


def test_can_earn_by_ad_false_once_daily_cap_used_up(out):
    """广告额度领完后 canEarnByAd 立刻为 false —— 页面据此在放视频前就拦住。

    这条守的是一个具体体验事故：按钮说「看广告 +1 次」，用户看完 30 秒
    才被告知「今天的领完了」。判断放在 quota 里，页面不得自己拼条件。
    """
    o = out["out"]
    assert o["canEarnAfterEnable"] is True
    assert o["canEarnAfterAdUsedUp"] is False


def test_share_bonus_adds_three_batches_and_caps_times(out):
    """转发一次 +3 批、每天最多领 2 次；第 3 次返回 capped，而不是假装成功。"""
    o = out["out"]
    assert [s["ok"] for s in o["shares"]] == [True, True, False]
    assert [s.get("added") for s in o["shares"][:2]] == [3, 3]
    assert o["shares"][2]["reason"] == "capped"
    assert o["afterShare"]["shareLeft"] == 0
    # 9 批已用完，领了 2 次共 +6 批 → 还剩 6 批
    assert o["afterShare"]["remaining"] == 6
    assert o["afterShare"]["used"] == 9


def test_ad_bonus_separate_from_share(out):
    """广告额度与转发额度各算各的，互不挤占。"""
    o = out["out"]
    assert o["canWatchAfterEnable"] is True
    assert [a["ok"] for a in o["ads"]] == [True, True, False]
    assert o["ads"][2]["reason"] == "capped"
    assert o["afterAd"]["adLeft"] == 0
    # 9 批用完 + 转发 +6 + 广告 +6
    assert o["afterAd"]["remaining"] == 12


def test_remaining_never_goes_negative(out):
    """额度用尽后继续点，计数不加、余量不为负。"""
    o = out["out"]
    assert [d["ok"] for d in o["drain"]] == [True] * 12 + [False]
    assert o["drain"][-1]["reason"] == "exhausted"
    assert o["afterDrain"]["remaining"] == 0
    # 9 免费 + 6 转发 + 6 广告 = 21
    assert o["afterDrain"]["used"] == 21


def test_resets_on_new_day(out):
    """跨天回到满额（用「昨天用满 99 批」验，避免把累加当成重置）。"""
    o = out["out"]["afterRollover"]
    assert o["used"] == 0
    assert o["remaining"] == 9
    assert o["shareLeft"] == 2
    assert o["adLeft"] == 2


def test_storage_failures_never_block_the_user(out):
    """读失败按满额（宁可多给一次），写失败静默（额度不值得弹错误）。"""
    o = out["out"]
    assert o["onReadError"]["remaining"] == 9
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
