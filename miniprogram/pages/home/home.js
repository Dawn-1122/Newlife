// 首页 = 一座门楼：两扇朱漆对开门即两个主入口（左「起名」右「释名」）。
// 点门 → 门绕轴旋转打开 → 进入对应功能；次级入口收在门楼下方极简文字链。
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')

Page({
  data: { bookCount: 0, opening: '' },

  onShow() {
    // 从别的页返回时复位开门状态，并重算名字本条数
    this.setData({
      bookCount: namebook.listRecords().length + namebook.listFavs().length,
      opening: ''
    })
  },

  onDoorTap(e) {
    const { door, url } = e.currentTarget.dataset
    if (this.data.opening) return // 已在开门动画中，防连点
    this.setData({ opening: door })
    // 等门完全打开再跳转，让动画完整呈现
    setTimeout(() => {
      if (url) wx.navigateTo({ url })
    }, 560)
  },

  onBookTap() {
    wx.navigateTo({ url: '/pages/history/history' })
  },

  onMoreTap() {
    wx.navigateTo({ url: '/pages/more/more' })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
