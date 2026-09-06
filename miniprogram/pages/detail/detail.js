const api = require('../../utils/api')

Page({
  data: {
    name: null,
    pinyinText: '',

    // 深度寓意（多层余味，分享解锁）
    unlocked: false,
    deepLoading: false,
    deepMeaning: null,
    layers: [],
    meaningSource: ''
  },

  onLoad() {
    const app = getApp()
    const name = app.globalData.selectedName

    if (!name) {
      wx.navigateBack()
      return
    }

    // 按起名批次单次解锁：分享一次，本批次所有名字的深度寓意均可看
    const batchId = app.globalData.lastBatchId || 'default'
    const unlocked = !!wx.getStorageSync('unlock_' + batchId)
    this.batchId = batchId

    this.setData({
      name,
      pinyinText: name.phonetics.pinyins.join(' · '),
      unlocked
    })

    if (unlocked) {
      this.loadDeepMeaning()
    }
  },

  async loadDeepMeaning() {
    const app = getApp()
    const name = this.data.name
    const params = app.globalData.lastParams || {}

    this.setData({ deepLoading: true })
    try {
      const result = await api.nameMeaning({
        full_name: name.full_name,
        gender: params.gender || 'male',
        year: params.year,
        month: params.month,
        day: params.day,
        hour: params.hour,
        minute: params.minute
      })
      this.setData({
        deepMeaning: result,
        layers: result.layers || [],
        meaningSource: result.meaning_source || '',
        deepLoading: false
      })
    } catch (err) {
      this.setData({ deepLoading: false })
      wx.showToast({ title: (err && err.message) || '深度解读加载失败', icon: 'none' })
    }
  },

  markUnlocked() {
    wx.setStorageSync('unlock_' + (this.batchId || 'default'), true)
    this.setData({ unlocked: true })
    if (!this.data.deepMeaning) {
      this.loadDeepMeaning()
    }
  },

  onCopyTap() {
    const name = this.data.name
    const poetry = name.poetry
      ? `\n出处：「${name.poetry.source}·${name.poetry.title}」\n${name.poetry.text}`
      : ''

    const text = `${name.full_name}\n综合评分: ${name.scores.overall}分${poetry}\n${name.meaning}`

    wx.setClipboardData({
      data: text,
      success() {
        wx.showToast({ title: '已复制', icon: 'success' })
      }
    })
  },

  onShareAppMessage() {
    const name = this.data.name
    return {
      title: `「${name.full_name}」综合评分${name.scores.overall}分`,
      path: '/pages/home/home',
      // 分享成功即解锁深度寓意
      success: () => {
        this.markUnlocked()
      }
    }
  }
})
