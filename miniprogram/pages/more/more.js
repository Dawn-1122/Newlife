// 二级菜单：主页只留「起名 / 释名」两个主入口，细分功能集中在这里。
// available:false 的行点按只提示「即将上线」。
const share = require('../../utils/share')

Page({
  data: {
    groups: [
      {
        title: '起名',
        items: [
          { key: 'baby', name: '给宝宝起名', url: '/pages/name/name', available: true },
          { key: 'prenatal', name: '孕期参考起名', url: '/pages/name/name?tab=prenatal', available: true },
          { key: 'rename', name: '成人改名', url: '', available: false },
          { key: 'creative', name: '创意起名', url: '', available: false },
          { key: 'pet', name: '宠物名', url: '', available: false },
          { key: 'brand', name: '品牌店名', url: '', available: false }
        ]
      },
      {
        title: '释名',
        items: [
          { key: 'analyze', name: '释现有名', url: '/pages/analyze/analyze', available: true },
          { key: 'candidate', name: '测候选名', url: '', available: false },
          { key: 'compare', name: '双名对比', url: '', available: false },
          { key: 'special', name: '专项测评', url: '', available: false }
        ]
      },
      {
        // 起名记录与收藏名字都落在本机（utils/namebook.js），换设备不会同步
        title: '我的',
        items: [
          { key: 'book', name: '我的名字本', url: '/pages/history/history', available: true }
        ]
      }
    ]
  },

  onRowTap(e) {
    const { url, available } = e.currentTarget.dataset
    if (!available || available === 'false') {
      wx.showToast({ title: '即将上线', icon: 'none' })
      return
    }
    if (url) wx.navigateTo({ url })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
