Page({
  data: {
    bazi: null,
    xiyongText: '',
    jiyongText: ''
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.lastResult

    if (!result || !result.bazi) {
      wx.navigateBack()
      return
    }

    const bazi = result.bazi

    // 预计算藏干文本
    const pillars = (bazi.pillars_detail || []).map(function(p) {
      p.cangganText = (p.canggan || []).map(function(c) {
        return c.gan + '(' + c.wuxing + '·' + c.level + ')'
      }).join('  ')
      return p
    })

    const xiyongText = bazi.xiyong.xi_wuxing.join('、')
    const jiyongText = bazi.xiyong.ji_wuxing.join('、')

    this.setData({
      bazi: Object.assign({}, bazi, { pillars_detail: pillars }),
      xiyongText,
      jiyongText
    })
  }
})
