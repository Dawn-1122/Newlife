Page({
  data: {
    name: null,
    pinyinText: ''
  },

  onLoad() {
    const app = getApp()
    const name = app.globalData.selectedName

    if (!name) {
      wx.navigateBack()
      return
    }

    this.setData({
      name,
      pinyinText: name.phonetics.pinyins.join(' · ')
    })
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
      path: '/pages/home/home'
    }
  }
})
