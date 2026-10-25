/**
 * 出生历法信息（原「八字详解」）
 *
 * 合规口径（2026-10-25）：四柱代表的含义不做解释，不预测命理，不提供建议。
 * 所以这一页只做两件事：把出生时间换算成干支历法（事实），
 * 再把干支上的五行标签数一遍（统计）。
 * 「日主强弱 / 喜神 / 用神 / 忌神 / 命局解释」这些判断性内容不再展示；
 * 后端仍在内部用它给选字加权，但那是排序权重，不是给用户看的结论。
 */
const share = require('../../utils/share')

Page({
  data: {
    bazi: null,
    // 时辰是否用户真填过。没填时按午时代入，四柱里的时柱不能当成事实展示
    hourKnown: true
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.lastResult

    if (!result || !result.bazi) {
      wx.navigateBack()
      return
    }

    const params = app.globalData.lastParams || {}
    const hourKnown = params.hour !== undefined && params.hour !== null

    const bazi = result.bazi

    // 预计算藏干文本
    const pillars = (bazi.pillars_detail || []).map(function (p) {
      p.cangganText = (p.canggan || []).map(function (c) {
        return c.gan + '(' + c.wuxing + '·' + c.level + ')'
      }).join('  ')
      // 时辰未知：时柱是内部代入的值，标出来，不当作已知事实
      p.unknown = p.position === 'hour' && !hourKnown
      return p
    })

    this.setData({
      bazi: Object.assign({}, bazi, { pillars_detail: pillars }),
      hourKnown: hourKnown
    })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
