const share = require('../../utils/share')

Page({
  data: {
    bazi: null,
    xiyongText: '',
    jiyongText: '',
    // 时辰是否用户真填过。没填时排盘按午时代入，四柱里的时柱不能当成事实展示
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
    const pillars = (bazi.pillars_detail || []).map(function(p) {
      p.cangganText = (p.canggan || []).map(function(c) {
        return c.gan + '(' + c.wuxing + '·' + c.level + ')'
      }).join('  ')
      // 时辰未知：时柱是内部代入的值，标出来，不当作已知事实
      p.unknown = p.position === 'hour' && !hourKnown
      return p
    })

    const xiyongText = bazi.xiyong.xi_wuxing.join('、')
    const jiyongText = bazi.xiyong.ji_wuxing.join('、')

    this.setData({
      bazi: Object.assign({}, bazi, { pillars_detail: pillars }),
      xiyongText,
      jiyongText,
      hourKnown: hourKnown
    })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
