Page({
  data: {
    bazi: null,
    names: [],
    xiyongText: '',
    wuxingList: []
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.lastResult

    if (!result) {
      wx.navigateBack()
      return
    }

    const wuxingList = []
    if (result.bazi && result.bazi.wuxing) {
      const pct = result.bazi.wuxing.percentages
      const order = ['金', '木', '水', '火', '土']
      for (const name of order) {
        wuxingList.push({ name, percent: pct[name] || 0 })
      }
    }

    const xiyongText = result.bazi
      ? result.bazi.xiyong.xi_wuxing.join('、')
      : ''

    // 给每个名字加上拼音展示文本
    const names = (result.names || []).map(function(n) {
      n.pinyinText = (n.phonetics && n.phonetics.pinyins) ? n.phonetics.pinyins.join(' · ') : ''
      return n
    })

    this.setData({
      bazi: result.bazi,
      names: names,
      xiyongText,
      wuxingList
    })
  },

  onNameTap(e) {
    const index = e.currentTarget.dataset.index
    const app = getApp()
    app.globalData.selectedName = app.globalData.lastResult.names[index]
    wx.navigateTo({
      url: '/pages/detail/detail'
    })
  }
})
