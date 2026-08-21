Page({
  data: {
    entries: [
      { key: 'baby', icon: '名', title: '给宝宝起名', desc: '产前参考 · 产后精确', available: true, url: '/pages/name/name' },
      { key: 'analyze', icon: '测', title: '名字测评', desc: '用字 · 音律 · 五格 · 出处', available: true, url: '/pages/analyze/analyze' },
      { key: 'rename', icon: '改', title: '成人改名', desc: '命局合参 · 逐步优化', available: false, url: '' },
      { key: 'creative', icon: '创', title: '创意起名', desc: '网名 · 笔名 · 艺名', available: false, url: '' }
    ],
    moreExpanded: false,
    moreEntries: [
      { key: 'pet', icon: '宠', title: '宠物名', available: false },
      { key: 'brand', icon: '牌', title: '品牌店名', available: false },
      { key: 'bilingual', icon: '译', title: '双语名', available: false }
    ]
  },

  onEntryTap(e) {
    const { key, url, available } = e.currentTarget.dataset
    if (available === false || available === 'false') {
      wx.showToast({ title: '即将上线', icon: 'none' })
      return
    }
    if (url) {
      wx.navigateTo({ url })
    }
  },

  onToggleMore() {
    this.setData({ moreExpanded: !this.data.moreExpanded })
  },

  onMoreEntryTap() {
    wx.showToast({ title: '即将上线', icon: 'none' })
  }
})
