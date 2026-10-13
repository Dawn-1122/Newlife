// 主页只承载两个主功能：起名 / 名字测评。
// 其余细分功能一律收进二级菜单 pages/more，主页不再挂说明小字。
const share = require('../../utils/share')

Page({
  data: {},

  onEntryTap(e) {
    const url = e.currentTarget.dataset.url
    if (url) wx.navigateTo({ url })
  },

  onMoreTap() {
    wx.navigateTo({ url: '/pages/more/more' })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
