// 主页只承载两个主功能：起名 / 名字测评。
// 其余细分功能一律收进二级菜单 pages/more，主页不再挂说明小字。
Page({
  data: {},

  onEntryTap(e) {
    const url = e.currentTarget.dataset.url
    if (url) wx.navigateTo({ url })
  },

  onMoreTap() {
    wx.navigateTo({ url: '/pages/more/more' })
  },

  onShareAppMessage() {
    return {
      title: '名堂 · 有据可循的起名工具',
      path: '/pages/home/home'
    }
  }
})
