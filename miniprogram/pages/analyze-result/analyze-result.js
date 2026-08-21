Page({
  data: {
    result: null,
    pinyinText: '',
    poetryList: [],
    matchedWuxingText: ''
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.analyzeResult

    if (!result) {
      wx.navigateBack()
      return
    }

    const phonetics = result.phonetics || {}
    const pinyinText = (phonetics.pinyins || []).join(' · ')

    const poetryList = result.poetry_list || (result.poetry ? [result.poetry] : [])

    let matchedWuxingText = ''
    if (result.bazi_match && result.bazi_match.matched_wuxing) {
      matchedWuxingText = result.bazi_match.matched_wuxing.join('、')
    }

    this.setData({
      result: result,
      pinyinText,
      poetryList,
      matchedWuxingText
    })
  },

  onBackHome() {
    wx.reLaunch({ url: '/pages/home/home' })
  }
})
