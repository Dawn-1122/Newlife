// 名字本：起名记录 + 收藏名字。
//
// 为什么有这个页面：
// 起名结果此前只存在于 app.globalData（内存），退出小程序就没了 ——
// 用户回不到「上次那批名字」，也留不住看中的那个名字。
// 落盘逻辑全在 utils/namebook.js（本地存储，单机、可离线）。
//
// 本页只做三件事：
//   1. 记录 → 把该批结果放回 globalData，再跳回原来的结果页（结果页只认 globalData）
//   2. 收藏 → 设置 selectedName 后进详情页，与从结果页点进去是同一条路径
//   3. 收藏项「对比」→ 加进待比名单（utils/compare.js），够两个就跳对比页
const namebook = require('../../utils/namebook')
const compare = require('../../utils/compare')
const share = require('../../utils/share')

Page({
  data: {
    tab: 'records',
    records: [],
    favs: [],
    // 上限写进页面：用户知道「最多存多少」才会明白为什么旧的会被清掉
    recordLimit: namebook.RECORD_LIMIT
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
      // 收藏 = 用户已经选定的名字。按产品原则（评分只作推荐分、不作等级分），
      // 这里不再折算「推荐值」：选定之后再给它打一个分数，等于在用户的选择上
      // 又压了一层评判，既没有意义也不礼貌。要看依据就点进详情页。
      favs: namebook.listFavs()
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

  /**
   * 把收藏的名字加入对比。
   *
   * 为什么从这里进：收藏是「已经选到最后的几个」，正是最需要并排看的时刻。
   * 队列在 utils/compare.js（跨页面共享），加满 3 个就不再接受 ——
   * 满了提示「先去掉一个」，不静默替换已加入的那个。
   */
  onFavCompare(e) {
    const name = e.currentTarget.dataset.name
    const ret = compare.add(name)

    if (!ret.ok) {
      wx.showToast({
        title: ret.full
          ? '最多并排 ' + compare.MAX + ' 个，先去掉一个'
          : (ret.error || '没能加入对比'),
        icon: 'none'
      })
      return
    }

    const count = (ret.names || []).length
    if (count < 2) {
      wx.showToast({ title: '已加入，再挑一个就能对照', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/compare/compare' })
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
