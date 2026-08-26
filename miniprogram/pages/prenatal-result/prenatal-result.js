const WUXING_ORDER = ['金', '木', '水', '火', '土']

function distToList(dist) {
  const list = []
  WUXING_ORDER.forEach(function (name) {
    const value = (dist && dist[name]) || 0
    list.push({ name: name, percent: Math.round(value * 100) })
  })
  return list
}

Page({
  data: {
    result: null,
    dayMasterDist: [],
    xiyongDist: [],
    stableWuxingText: '',
    safeChars: [],
    note: ''
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.prenatalResult

    if (!result) {
      wx.navigateBack()
      return
    }

    const probabilistic = result.probabilistic || {}
    const stable = (result.suggestion && result.suggestion.stable_wuxing) || []

    this.setData({
      result: result,
      dayMasterDist: distToList(probabilistic.day_master_wuxing_dist),
      xiyongDist: distToList(probabilistic.xiyong_wuxing_dist),
      stableWuxingText: stable.join('、'),
      safeChars: (result.suggestion && result.suggestion.safe_chars) || [],
      note: (result.suggestion && result.suggestion.note) || ''
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
  }
})
