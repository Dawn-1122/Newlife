const share = require('../../utils/share')

Page({
  data: {
    result: null,
    pinyinText: '',
    poetryList: [],
    matchedWuxingText: '',
    // 收束语（后端 name_verdict.py 生成）。旧记录没有这个字段，判空后不显示
    verdict: '',
    // 时辰是否用户真填过。旧记录（本次改动之前存的）没有这个字段，
    // 一律按「已知」处理 —— 不能给老数据凭空补一个「时辰未填」的提示
    hourKnown: true
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
      matchedWuxingText,
      verdict: result.verdict || '',
      hourKnown: result.hour_known !== false
    })
  },

  onBackHome() {
    wx.reLaunch({ url: '/pages/home/home' })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
