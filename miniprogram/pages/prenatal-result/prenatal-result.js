/**
 * 孕期范围参考 · 只出统计，不出结论
 *
 * 合规口径（2026-10-25）：不预测命理、不提供建议。所以这一页只把
 * 「预产期浮动范围内每一天的干支五行」数一遍，给出占比；
 * 「喜用神分布」「稳定五行」「安全候选字」这些判断性内容一律不展示 ——
 * 给未出生的孩子推断喜用五行，本身就是预测命理。
 */
const share = require('../../utils/share')

const WUXING_ORDER = ['金', '木', '水', '火', '土']

/**
 * {五行: 0~1} → [{name, percent}]
 *
 * 用「最大余数法」分配那 100 个百分点：逐项四舍五入会让五项加起来变成
 * 99% 或 101%，而这一页唯一的内容就是这组统计 —— 加起来不等于 100，
 * 用户第一眼就会怀疑数据是编的。所以先取整、再把差的那几个百分点
 * 按小数部分从大到小补齐。
 */
function distToList(dist) {
  const rows = WUXING_ORDER.map(function (name) {
    const value = ((dist && dist[name]) || 0) * 100
    const base = Math.floor(value)
    return { name: name, percent: base, rest: value - base }
  })

  const total = WUXING_ORDER.reduce(function (sum, name) {
    return sum + (((dist && dist[name]) || 0) * 100)
  }, 0)
  if (total <= 0) {
    return rows.map(function (r) { return { name: r.name, percent: 0 } })
  }

  let diff = 100 - rows.reduce(function (sum, r) { return sum + r.percent }, 0)
  // slice() 里是同一批对象引用，排序后改 percent 就是改原对象
  rows.slice().sort(function (a, b) { return b.rest - a.rest }).forEach(function (r) {
    if (diff > 0) {
      r.percent += 1
      diff -= 1
    }
  })

  return rows.map(function (r) { return { name: r.name, percent: r.percent } })
}

Page({
  data: {
    result: null,
    // 逐日排盘统计出的日柱天干五行占比（纯计数）
    dayMasterDist: [],
    // 浮窗范围内的总天数，用于说明「百分比是按几天算的」
    totalDays: 0
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.prenatalResult

    if (!result) {
      wx.navigateBack()
      return
    }

    const probabilistic = result.probabilistic || {}
    const rangeDays = result.range_days || 0

    this.setData({
      result: result,
      dayMasterDist: distToList(probabilistic.day_master_wuxing_dist),
      totalDays: rangeDays * 2 + 1
    })
  },

  onAdjustPref() {
    const app = getApp()
    const params = app.globalData.lastParams

    if (!params) {
      wx.showToast({ title: '请求参数已失效，请重新起名', icon: 'none' })
      return
    }

    app.globalData.draftParams = params
    app.globalData.draftTab = 'prenatal'
    wx.navigateTo({ url: '/pages/wizard/wizard' })
  },

  onBackHome() {
    wx.reLaunch({ url: '/pages/home/home' })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
