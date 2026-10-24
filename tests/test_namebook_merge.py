"""名字本合并规则回归测试（miniprogram/utils/namebook.js）。

为什么用 node 跑前端 JS：合并逻辑（参数指纹 / 批次累计 / 上限清理）全在前端，
后端测试测不到。而这段逻辑错一次，用户丢的就是「上次那批名字」——
正是本次要修的 P0。故直接用 node 载入 namebook.js，用内存版 wx 存储跑一遍。

三条约束（对应评审 P0-2）：
1. 同一次起名「换一批」多批 → 合并成一条，候选名去重累计，batches 递增；
2. 换个条件起名 → 新开一条，不并进上一条；
3. 超出条数上限 → 返回 dropped，不再静默丢弃。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NAMEBOOK_JS = PROJECT_ROOT / "miniprogram" / "utils" / "namebook.js"

_NODE = shutil.which("node") or shutil.which("nodejs")

# node 脚本：内存版 wx 存储 + 四段场景，把结果原样吐给 Python 断言。
# 存储用 JSON 深拷贝，顺带能暴露「返回对象与存入对象共享引用」这类问题。
_SCRIPT = r"""
const store = {}
global.wx = {
  getStorageSync(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : '' },
  setStorageSync(k, v) { store[k] = JSON.parse(JSON.stringify(v)) },
  removeStorageSync(k) { delete store[k] },
  showToast() {}
}
const nb = require(process.argv[1])

const BASE = { surname: '林', gender: 'male', name_length: 2, style: 'classic' }
const name = (full) => ({ full_name: full, given_name: full.slice(1), scores: { overall: 80 } })

// ── 场景 1：同条件换一批 ──
const a1 = nb.addRecord(nb.buildRecord('postnatal', BASE, { names: [name('林清野')], bazi: {} }, 111))
const a2 = nb.addRecord(nb.buildRecord(
  'postnatal',
  Object.assign({}, BASE, { exclude_names: ['林清野'] }),   // 换一批会带排除名单
  { names: [name('林素秋')], bazi: {} },
  222
))
const merged = nb.listRecords()

// ── 场景 2：换条件起名（姓不同）──
const a3 = nb.addRecord(nb.buildRecord(
  'postnatal',
  { surname: '顾', gender: 'female', name_length: 2 },
  { names: [name('顾清和')], bazi: {} },
  333
))
const afterNewCondition = nb.listRecords()

// ── 场景 3：释名同一个名字查两次 ──
nb.addRecord(nb.buildRecord('analyze', { full_name: '林清野', gender: 'male' }, { full_name: '林清野', phonetics: { score: 90 } }, 0))
const an2 = nb.addRecord(nb.buildRecord('analyze', { full_name: '林清野', gender: 'male' }, { full_name: '林清野', phonetics: { score: 92 } }, 0))
const analyzeRecords = nb.listRecords().filter((r) => r.kind === 'analyze')

// ── 场景 4：条数上限 ──
nb.clearRecords()
let last = null
for (let i = 0; i < 25; i++) {
  last = nb.addRecord(nb.buildRecord(
    'postnatal',
    { surname: '姓' + i, gender: 'male', name_length: 2 },
    { names: [name('名字' + i)], bazi: {} },
    i
  ))
}
const capped = nb.listRecords()

process.stdout.write(JSON.stringify({
  limit: nb.RECORD_LIMIT,
  mergeMax: nb.MERGE_MAX_NAMES,
  s1: { first: a1.merged, second: a2.merged, dropped: a2.dropped },
  mergedCount: merged.length,
  mergedNames: (merged[0].payload.names || []).map((n) => n.full_name),
  mergedBatches: merged[0].batches,
  mergedBatchId: merged[0].batchId,
  mergedSubtitle: merged[0].subtitle,
  newConditionCount: afterNewCondition.length,
  newConditionFirstTitle: afterNewCondition[0].title,
  analyze: { merged: an2.merged, count: analyzeRecords.length, batches: analyzeRecords[0].batches },
  cap: { count: capped.length, dropped: last.dropped }
}))
"""


@pytest.fixture(scope="module")
def result() -> dict:
    if not _NODE:
        pytest.skip("未找到 node，跳过名字本合并测试")
    out = subprocess.run(
        [_NODE, "-e", _SCRIPT, str(NAMEBOOK_JS)],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(out.stdout)


def test_same_params_merge_into_one_record(result):
    """同条件换一批不新开记录：两批只留一条。"""
    assert result["s1"]["first"] is False, "第一条记录不该是合并（此前无同键记录）"
    assert result["s1"]["second"] is True, "同条件的第二批必须并进原记录"
    assert result["mergedCount"] == 1


def test_merged_record_keeps_all_names(result):
    """合并后候选名累计去重 —— 早期批次的名字不能被顶掉（否则等于丢了）。"""
    assert result["mergedNames"] == ["林素秋", "林清野"], "新一批在前、旧批次在后"


def test_merged_record_counts_batches(result):
    """batches 递增、batchId 跟最新一批（深度寓意按批次解锁）。"""
    assert result["mergedBatches"] == 2
    assert result["mergedBatchId"] == 222
    assert "翻 2 批" in result["mergedSubtitle"]


def test_different_params_open_new_record(result):
    """换条件（姓不同）必须新开一条，不能并进上一次起名。"""
    assert result["newConditionCount"] == 2
    assert result["newConditionFirstTitle"].startswith("顾")


def test_analyze_same_name_merges(result):
    """释名同一个名字查两次：一条记录、次数记 2。"""
    assert result["analyze"]["merged"] is True
    assert result["analyze"]["count"] == 1
    assert result["analyze"]["batches"] == 2


def test_record_limit_reports_dropped(result):
    """超上限要回传 dropped，不再静默丢最旧的一条。

    dropped 是「本次调用清理了几条」，不是累计值：到了上限之后，
    每新增一条正好挤掉一条，所以第 25 次新增的 dropped 是 1。
    """
    assert result["limit"] == 20
    assert result["cap"]["count"] == result["limit"]
    assert result["cap"]["dropped"] == 1
