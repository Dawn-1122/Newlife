// 首页 = 一幅门楼水墨画：牌匾题「名堂」，两个小人即入口——
// 左小人（书案+「起名」旗）进起名流程，右小人（「释名」签+八卦布）进释名。
// 热区透明覆盖在画上（见 home.wxss .hotspot-*），按压显淡朱细框。
const share = require('../../utils/share')

Page({
  onEntryTap(e) {
    const { url } = e.currentTarget.dataset
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
