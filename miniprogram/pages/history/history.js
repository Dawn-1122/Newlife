// 名字本：起名记录 + 收藏名字。
//
// 为什么有这个页面：
// 起名结果此前只存在于 app.globalData（内存），退出小程序就没了 ——
// 用户回不到「上次那批名字」，也留不住看中的那个名字。
// 落盘逻辑全在 utils/namebook.js（本地存储，单机、可离线）。
//
// 本页只做两件事：
//   1. 记录 → 把该批结果放回 globalData，再跳回原来的结果页（结果页只认 globalData）
//   2. 收藏 → 设置 selectedName 后进详情页，与从结果页点进去是同一条路径
const namebook = require('../../utils/namebook')
const share = require('../../utils/share')
const score = require('../../utils/score')

Page({
  data: {
    tab: 'records',
    records: [],
    favs: []
  },

  onLoad() {
    this.refresh()
  },

  // 从结果页返回时可能有新收藏/新记录，回来时重读一次
  onShow() {
    this.refresh()
  },

  refresh() {
    this.setData({
      records: namebook.listRecords(),
      // 收藏项只存了 overall 原分，展示用的推荐值在读的时候算，
      // 这样旧记录和新记录是同一把尺子（换算见 utils/score.js）
      favs: namebook.listFavs().map(function (f) {
        return Object.assign({}, f, score.badge(f.overall))
      })
    })
  },

  onTabTap(e) {
    this.setData({ tab: e.currentTarget.dataset.tab })
  },

  // ── 记录：恢复该批上下文后跳回原结果页 ──
  onRecordTap(e) {
    const record = namebook.getRecord(e.currentTarget.dataset.id)
    if (!record) {
      wx.showToast({ title: '记录已不存在', icon: 'none' })
      this.refresh()
      return
    }

    const app = getApp()

    if (record.kind === 'postnatal') {
      app.globalData.lastResult = record.payload
      app.globalData.lastParams = record.params
      // 批次号要带回去，否则深度寓意的解锁状态对不上
      app.globalData.lastBatchId = record.batchId || Date.now()
      // 排除名单跟着切换：否则在这条记录里点「换一批」，被排除的是别的记录的名字
      app.globalData.shownNames = ((record.payload && record.payload.names) || [])
        .map(function (n) { return n.given_name })
      wx.navigateTo({ url: '/pages/result/result' })
      return
    }

    if (record.kind === 'prenatal') {
      app.globalData.prenatalResult = record.payload
      app.globalData.lastParams = record.params
      wx.navigateTo({ url: '/pages/prenatal-result/prenatal-result' })
      return
    }

    app.globalData.analyzeResult = record.payload
    wx.navigateTo({ url: '/pages/analyze-result/analyze-result' })
  },

  onRecordDelete(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '删除这条记录',
      content: '删除后这条起名记录不再保留，收藏的名字不受影响。',
      confirmText: '删除',
      confirmColor: '#A6321F',
      success: (res) => {
        if (!res.confirm) return
        const ret = namebook.removeRecord(id)
        if (!ret.ok) {
          wx.showToast({ title: ret.error, icon: 'none' })
        }
        this.refresh()
      }
    })
  },

  // ── 收藏：进名字详情（与从结果页点名字是同一条路径）──
  onFavTap(e) {
    const id = e.currentTarget.dataset.id
    let fav = null
    namebook.listFavs().forEach(function (f) {
      if (f.id === id) fav = f
    })

    if (!fav) {
      wx.showToast({ title: '该收藏已不存在', icon: 'none' })
      this.refresh()
      return
    }

    const app = getApp()
    app.globalData.selectedName = fav.data
    app.globalData.lastParams = fav.params || {}
    app.globalData.lastBatchId = fav.batchId || 0

    wx.navigateTo({ url: '/pages/detail/detail' })
  },

  onFavDelete(e) {
    const id = e.currentTarget.dataset.id
    const ret = namebook.removeFav(id)
    if (!ret.ok) {
      wx.showToast({ title: ret.error, icon: 'none' })
    } else {
      wx.showToast({ title: '已取消收藏', icon: 'none' })
    }
    this.refresh()
  },

  onClearTap() {
    const isRecords = this.data.tab === 'records'
    wx.showModal({
      title: isRecords ? '清空起名记录' : '清空收藏',
      content: isRecords
        ? '将删除本机保存的全部起名记录（收藏的名字不受影响）。此操作不可撤销。'
        : '将删除本机保存的全部收藏名字。此操作不可撤销。',
      confirmText: '清空',
      confirmColor: '#A6321F',
      success: (res) => {
        if (!res.confirm) return
        const ret = isRecords ? namebook.clearRecords() : namebook.clearFavs()
        if (!ret.ok) {
          wx.showToast({ title: ret.error, icon: 'none' })
        }
        this.refresh()
      }
    })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
