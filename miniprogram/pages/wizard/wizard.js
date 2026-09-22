const api = require('../../utils/api')

// 起名第二步（也是最后一步）：挑一种「感觉」→ 直接生成。
//
// 旧版这里是 7 步向导（方式/风格/寓意/避讳/确认/来源/选字），
// 其中「寓意优先 or 命格优先」对用户是算法口径而非选择，体验割裂；
// 现压成两步：第一步在 pages/name 填资料，第二步只挑一张感觉卡。
// 意境来源与用字筛选下沉到结果页（pages/result）。
Page({
  data: {
    tab: 'postnatal',
    feelings: [],
    selected: '',
    selectedTitle: '',
    metaText: '',
    avoidChars: '',
    avoidOpen: false,
    loading: false
  },

  onLoad() {
    const app = getApp()
    this.draft = Object.assign({}, app.globalData.draftParams || {})
    const tab = app.globalData.draftTab ||
      (this.draft.due_date ? 'prenatal' : 'postnatal')

    // 回填：从结果页「调整偏好」返回时，draft 里带着上次的 style
    const selected = this.draft.style || ''

    this.setData({
      tab: tab,
      feelings: this.buildFeelings(selected),
      selected: selected,
      selectedTitle: this.titleOf(selected),
      metaText: this.buildMeta(tab, this.draft),
      avoidChars: (this.draft.avoid_chars || []).join(',')
    })
  },

  buildFeelings(selected) {
    return (api.FEELING_CARDS || []).map(function (c) {
      return {
        code: c.code,
        title: c.title,
        imagery: c.imagery,
        selected: c.code === selected
      }
    })
  },

  titleOf(code) {
    let title = ''
    ;(api.FEELING_CARDS || []).forEach(function (c) {
      if (c.code === code) title = c.title
    })
    return title
  },

  // 顶部一行上下文，让用户确认「在给谁起名」
  buildMeta(tab, draft) {
    if (tab === 'prenatal') {
      return '预产期 ' + (draft.due_date || '未设置') + ' · ±' + (draft.range_days || 0) + '天'
    }
    const parts = []
    if (draft.surname) parts.push(draft.surname)
    parts.push(draft.gender === 'female' ? '女孩' : '男孩')
    parts.push(draft.name_length === 1 ? '单字名' : '双字名')
    return parts.join(' · ')
  },

  onFeelTap(e) {
    const code = e.currentTarget.dataset.code
    // 再点一次取消，允许「不设偏好、全方向生成」
    const next = this.data.selected === code ? '' : code
    this.setData({
      feelings: this.buildFeelings(next),
      selected: next,
      selectedTitle: this.titleOf(next)
    })
  },

  onToggleAvoid() {
    this.setData({ avoidOpen: !this.data.avoidOpen })
  },

  onAvoidInput(e) {
    this.setData({ avoidChars: e.detail.value })
  },

  parseAvoidChars() {
    const chars = []
    ;(this.data.avoidChars || '').split(/[,，、\s]+/).forEach(function (seg) {
      if (seg) chars.push(seg)
    })
    return chars
  },

  async onSubmit() {
    const params = Object.assign({}, this.draft)

    // 剥离展示用字段，避免透传给后端
    delete params.birthDate
    delete params.hourText

    // 感觉卡 → 后端两个既有偏好维度（style 单选 + meanings 多选）
    const card = (api.FEELING_CARDS || []).filter(function (c) {
      return c.code === this.data.selected
    }.bind(this))[0]

    if (card) {
      params.style = card.style
      params.meanings = card.meanings.slice()
    } else {
      delete params.style
      delete params.meanings
    }

    const avoidChars = this.parseAvoidChars()
    if (avoidChars.length) {
      params.avoid_chars = avoidChars
    } else {
      delete params.avoid_chars
    }

    const app = getApp()
    this.setData({ loading: true })
    try {
      if (this.data.tab === 'prenatal') {
        const result = await api.prenatal(params)
        app.globalData.prenatalResult = result
        app.globalData.lastParams = params
        wx.navigateTo({ url: '/pages/prenatal-result/prenatal-result' })
      } else {
        const result = await api.generateNames(params)
        app.globalData.lastResult = result
        app.globalData.lastParams = params
        // 每次起名 = 一个批次，深度寓意按批次单次解锁
        app.globalData.lastBatchId = Date.now()
        wx.navigateTo({ url: '/pages/result/result' })
      }
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '起名失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onShareAppMessage() {
    return {
      title: '名堂 · 有据可循的起名工具',
      path: '/pages/home/home'
    }
  }
})
