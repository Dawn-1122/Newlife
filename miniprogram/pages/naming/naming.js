// 起名类型选择页：宝宝起名（已实现）可进，其余类型灰显「即将上线」。
const share = require('../../utils/share')

Page({
  onTypeTap(e) {
    const { url } = e.currentTarget.dataset
    if (url) wx.navigateTo({ url })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
