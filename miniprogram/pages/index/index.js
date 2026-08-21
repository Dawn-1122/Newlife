Page({
  onLoad() {
    // 旧路径兜底：功能已平迁至 pages/name，首页改为 pages/home，重定向避免白屏
    wx.redirectTo({ url: '/pages/home/home' })
  }
})
