const api = require('../../utils/api')

// 诗词出处 → 前端风格筛选归类（与后端 STYLE_OPTIONS 的 source_preference 对应）
function getStyleCode(name) {
  const source = (name.poetry && name.poetry.source) || ''
  if (source === '诗经' || source === '楚辞' || source === '汉魏古诗') return 'classic'
  if (source === '唐诗' || source === '宋词') return 'modern'
  if (source === '经史子集') return 'grand'
  return ''
}

Page({
  data: {
    bazi: null,
    allNames: [],
    names: [],
    xiyongText: '',
    wuxingList: [],
    wuxingFilter: '',
    styleFilter: '',
    loading: false,
    fallbackNote: '',

    wuxingFilters: [
      { code: '', name: '全部' },
      { code: '金', name: '金' },
      { code: '木', name: '木' },
      { code: '水', name: '水' },
      { code: '火', name: '火' },
      { code: '土', name: '土' }
    ],
    styleFilters: [
      { code: '', name: '全部' },
      { code: 'classic', name: '古风' },
      { code: 'modern', name: '现代' },
      { code: 'grand', name: '大气' }
    ]
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.lastResult

    if (!result) {
      wx.navigateBack()
      return
    }

    this.renderResult(result)
  },

  renderResult(result) {
    const wuxingList = []
    if (result.bazi && result.bazi.wuxing) {
      const pct = result.bazi.wuxing.percentages
      const order = ['金', '木', '水', '火', '土']
      for (const name of order) {
        wuxingList.push({ name, percent: pct[name] || 0 })
      }
    }

    const xiyongText = result.bazi
      ? result.bazi.xiyong.xi_wuxing.join('、')
      : ''

    // 给每个名字加上拼音展示文本，作为全量候选池
    const allNames = (result.names || []).map(function (n) {
      n.pinyinText = (n.phonetics && n.phonetics.pinyins) ? n.phonetics.pinyins.join(' · ') : ''
      return n
    })

    this.setData({
      bazi: result.bazi,
      allNames: allNames,
      xiyongText: xiyongText,
      wuxingList: wuxingList,
      fallbackNote: result.fallback_note || ''
    })
    this.applyFilter()
  },

  applyFilter() {
    const wuxingFilter = this.data.wuxingFilter
    const styleFilter = this.data.styleFilter

    const names = this.data.allNames.filter(function (n) {
      if (wuxingFilter) {
        const chars = n.chars_info || []
        let hit = false
        for (let i = 0; i < chars.length; i++) {
          if (chars[i].wuxing === wuxingFilter) {
            hit = true
            break
          }
        }
        if (!hit) return false
      }

      if (styleFilter) {
        if (getStyleCode(n) !== styleFilter) return false
      }

      return true
    })

    this.setData({ names: names })
  },

  onWuxingFilterTap(e) {
    this.setData({ wuxingFilter: e.currentTarget.dataset.code })
    this.applyFilter()
  },

  onStyleFilterTap(e) {
    this.setData({ styleFilter: e.currentTarget.dataset.code })
    this.applyFilter()
  },

  async onRefresh() {
    if (this.data.loading) return

    const app = getApp()
    const params = app.globalData.lastParams

    if (!params) {
      wx.showToast({ title: '请求参数已失效，请重新起名', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    try {
      // 复用原始请求参数重新调用；后端无固定 seed，天然得到不同候选
      const result = await api.generateNames(params)
      app.globalData.lastResult = result
      // 换一批后重置筛选，展示全新候选
      this.setData({ wuxingFilter: '', styleFilter: '' })
      this.renderResult(result)
      wx.showToast({ title: '已换一批', icon: 'none' })
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '换一批失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onNameTap(e) {
    const index = e.currentTarget.dataset.index
    const app = getApp()
    app.globalData.selectedName = this.data.names[index]
    wx.navigateTo({
      url: '/pages/detail/detail'
    })
  },

  onBaziTap() {
    wx.navigateTo({
      url: '/pages/bazi/bazi'
    })
  },

  onAdjustPref() {
    const app = getApp()
    const params = app.globalData.lastParams

    if (!params) {
      wx.showToast({ title: '请求参数已失效，请重新起名', icon: 'none' })
      return
    }

    // 携带上次完整参数回跳 wizard 并回填
    app.globalData.draftParams = params
    app.globalData.draftTab = params.due_date ? 'prenatal' : 'postnatal'
    wx.navigateTo({ url: '/pages/wizard/wizard' })
  },

  onBackHome() {
    wx.reLaunch({ url: '/pages/home/home' })
  },

  onShareAppMessage() {
    return {
      title: '美名集 · 有据可循的起名工具',
      path: '/pages/home/home'
    }
  }
})
