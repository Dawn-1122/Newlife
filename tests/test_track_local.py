"""本地埋点约束（miniprogram/utils/track.js）。

三种埋点都只落本机：**不联网、不带身份信息**。这不是实现细节，
是产品评审 P0-4 的前置条件 —— 账号体系与隐私协议补齐之前，
埋点只允许做「这台设备上记了几个数」。

用 node 载入真实模块跑一遍（内存版 wx 存储），把约束变成可执行断言：
1. 只写本地存储，不发任何请求；
2. 计数与按天计数都递增；
3. 按天记录只留最近 30 天。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRACK_JS = PROJECT_ROOT / "miniprogram" / "utils" / "track.js"

_NODE = shutil.which("node") or shutil.which("nodejs")

_SCRIPT = r"""
const store = {}
let requests = 0
global.wx = {
  getStorageSync(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : '' },
  setStorageSync(k, v) { store[k] = JSON.parse(JSON.stringify(v)) },
  removeStorageSync(k) { delete store[k] },
  // 只要有人调用 request，就说明埋点跑到网络上了
  request() { requests++; throw new Error('埋点不该发请求') }
}
const t = require(process.argv[1])

t.track(t.TRACK.namingSubmit, { kind: 'postnatal', style: 'classic' })
t.track(t.TRACK.namingSubmit, { kind: 'postnatal', style: 'classic' })
t.track(t.TRACK.namingRefresh)
t.track(t.TRACK.favToggle, { added: 'yes' })

const summary = t.summary()

// 塞 40 天假数据，看是否只留 30 天
for (let i = 1; i <= 40; i++) {
  const d = new Date(2026, 0, 1)
  d.setDate(d.getDate() + i)
  const m = d.getMonth() + 1
  const day = d.getDate()
  const key = d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day)
  store['mt_track_v1'].days[key] = { naming_submit: 1 }
}
t.track(t.TRACK.namingSubmit, { kind: 'postnatal', style: 'classic' })
const afterTrim = store['mt_track_v1']

t.clear()

process.stdout.write(JSON.stringify({
  summary,
  requests,
  dayCount: Object.keys(afterTrim.days).length,
  cleared: !Object.prototype.hasOwnProperty.call(store, 'mt_track_v1')
}))
"""


@pytest.fixture(scope="module")
def result() -> dict:
    if not _NODE:
        pytest.skip("未找到 node，跳过埋点测试")
    out = subprocess.run(
        [_NODE, "-e", _SCRIPT, str(TRACK_JS)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(out.stdout)


def test_no_network_call(result):
    """埋点只落本机：账号与隐私协议补齐之前，不许往上报。"""
    assert result["requests"] == 0


def test_counts_accumulate(result):
    s = result["summary"]
    assert s["naming_submit"] == 2
    assert s["naming_refresh"] == 1
    assert s["fav_toggle"] == 1


def test_dimension_counts_kept_as_tallies_not_logs(result):
    """附加维度只做计数（键里带值），不存明细 —— 免得这个 key 变成行为日志。"""
    s = result["summary"]
    assert s["naming_submit.kind:postnatal"] == 2
    assert s["naming_submit.style:classic"] == 2
    assert s["fav_toggle.added:yes"] == 1


def test_days_trimmed_to_30(result):
    assert result["dayCount"] == 30


def test_clear_removes_key(result):
    assert result["cleared"] is True


def test_no_identity_fields():
    """源码里不许出现身份/网络相关的调用（守住「只落本机」这条线）。"""
    src = TRACK_JS.read_text(encoding="utf-8")
    for banned in ("wx.request", "wx.login", "wx.getUserInfo", "openid", "http://", "https://"):
        assert banned not in src, f"track.js 出现了 {banned}，埋点必须只落本机"
