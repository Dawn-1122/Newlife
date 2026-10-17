// 主页只承载两个主功能：起名 / 释名。
// 其余细分功能一律收进二级菜单 pages/more，主页不再挂说明小字。
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')

Page({
  // 名字本的条数（记录 + 收藏）：只在从别的页回来时才会变，故在 onShow 里重算
  data: { bookCount: 0 },

  onShow() {
    this.setData({
      bookCount: namebook.listRecords().length + namebook.listFavs().length
    })
  },

  onEntryTap(e) {
    const url = e.currentTarget.dataset.url
    if (url) wx.navigateTo({ url })
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
