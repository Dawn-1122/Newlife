const api = require('../../utils/api')

// 把风格示例卡转为带展示文本的卡片（单选项回填 selected）
function buildStyles(selectedCode) {
  return (api.STYLE_EXAMPLES || []).map(function (s) {
    const examplesText = (s.examples || []).map(function (e) {
      return e.name + (e.source ? '(' + e.source + ')' : '')
    }).join(' · ')
    return {
      code: s.code,
      name: s.name,
      feeling: s.feeling,
      examplesText: examplesText,
      selected: s.code === selectedCode
    }
  })
}

// 把寓意示例卡转为带展示文本的卡片（多选项回填 selected）
function buildMeanings(selectedCodes) {
  const set = {}
  ;(selectedCodes || []).forEach(function (c) { set[c] = true })
  return (api.MEANING_EXAMPLES || []).map(function (m) {
    return {
      code: m.code,
      name: m.name,
      feeling: m.feeling,
      examplesText: (m.examples || []).join(' / '),
      selected: !!set[m.code]
    }
  })
}

Page({
  data: {
    step: 1,
    progress: 25,
    stepTitle: '选择风格',
    tab: 'postnatal',
    styles: [],
    meanings: [],
    avoidChars: '',
    selectedStyleName: '',
    selectedMeaningNames: [],
    selectedMeaningText: '',
    baseLines: [],
    loading: false
  },

  onLoad() {
    const app = getApp()
    this.draft = app.globalData.draftParams || {}
    const tab = app.globalData.draftTab || (this.draft.due_date ? 'prenatal' : 'postnatal')

    const style = this.draft.style || ''
    const meanings = this.draft.meanings || []
    const avoidChars = (this.draft.avoid_chars || []).join(',')

    this.setData({
      tab: tab,
      styles: buildStyles(style),
      meanings: buildMeanings(meanings),
      avoidChars: avoidChars
    })
    this.refreshStepTitle()
    this.refreshSummary()
  },

  getSelectedStyle() {
    let result = ''
    this.data.styles.forEach(function (s) {
      if (s.selected) result = s.code
    })
    return result
  },

  getSelectedMeanings() {
    const result = []
    this.data.meanings.forEach(function (m) {
      if (m.selected) result.push(m.code)
    })
    return result
  },

  parseAvoidChars() {
    const raw = this.data.avoidChars || ''
    const chars = []
    raw.split(/[,，、\s]+/).forEach(function (seg) {
      if (seg) chars.push(seg)
    })
    return chars
  },

  refreshStepTitle() {
    const titles = { 1: '选择风格', 2: '选择寓意', 3: '避讳字', 4: '确认信息' }
    this.setData({ stepTitle: titles[this.data.step] || '' })
  },

  refreshSummary() {
    const draft = this.draft || {}
    const baseLines = []

    if (this.data.tab === 'prenatal') {
      baseLines.push({ label: '预产期', value: draft.due_date || '未设置' })
      baseLines.push({ label: '浮动范围', value: '±' + (draft.range_days || 0) + '天' })
    } else {
      baseLines.push({ label: '姓氏', value: draft.surname || '未设置' })
      baseLines.push({ label: '出生日期', value: this.formatBirth(draft) })
      baseLines.push({ label: '名字字数', value: draft.name_length === 1 ? '单字名' : '双字名' })
    }
    baseLines.push({ label: '性别', value: draft.gender === 'female' ? '女孩' : '男孩' })

    const selectedStyleName = this.styleNameOf(this.getSelectedStyle())
    const selectedMeaningCodes = this.getSelectedMeanings()
    const selectedMeaningNames = []
    const self = this
    selectedMeaningCodes.forEach(function (code) {
      selectedMeaningNames.push(self.meaningNameOf(code))
    })

    this.setData({
      baseLines: baseLines,
      selectedStyleName: selectedStyleName,
      selectedMeaningNames: selectedMeaningNames,
      selectedMeaningText: selectedMeaningNames.join('、'),
      avoidChars: this.data.avoidChars
    })
  },

  formatBirth(draft) {
    if (draft.birthDate) return draft.birthDate
    if (draft.year) {
      const m = ('0' + (draft.month || 1)).slice(-2)
      const d = ('0' + (draft.day || 1)).slice(-2)
      return draft.year + '-' + m + '-' + d
    }
    return '未设置'
  },

  styleNameOf(code) {
    let name = ''
    this.data.styles.forEach(function (s) {
      if (s.code === code) name = s.name
    })
    return name
  },

  meaningNameOf(code) {
    let name = ''
    this.data.meanings.forEach(function (m) {
      if (m.code === code) name = m.name
    })
    return name
  },

  onStyleTap(e) {
    const code = e.currentTarget.dataset.code
    const current = this.getSelectedStyle()
    const next = current === code ? '' : code
    this.setData({ styles: buildStyles(next) })
    this.refreshSummary()
  },

  onMeaningTap(e) {
    const code = e.currentTarget.dataset.code
    const selected = this.getSelectedMeanings()
    const idx = selected.indexOf(code)
    if (idx >= 0) {
      selected.splice(idx, 1)
    } else if (selected.length >= api.MEANING_MAX_SELECT) {
      wx.showToast({ title: '最多选 3 个寓意', icon: 'none' })
      return
    } else {
      selected.push(code)
    }
    this.setData({ meanings: buildMeanings(selected) })
    this.refreshSummary()
  },

  onAvoidInput(e) {
    this.setData({ avoidChars: e.detail.value })
  },

  goStep(step) {
    const clamped = Math.max(1, Math.min(4, step))
    this.setData({ step: clamped, progress: clamped * 25 })
    this.refreshStepTitle()
  },

  onNext() {
    this.goStep(this.data.step + 1)
  },

  onPrev() {
    this.goStep(this.data.step - 1)
  },

  onSkip() {
    this.onNext()
  },

  onJumpStep(e) {
    const step = Number(e.currentTarget.dataset.step)
    if (step >= 1 && step <= 4) this.goStep(step)
  },

  async onSubmit() {
    const draft = this.draft || {}
    const params = Object.assign({}, draft)

    // 剥离展示用字段，避免透传给后端
    delete params.birthDate
    delete params.hourText

    const style = this.getSelectedStyle()
    const meanings = this.getSelectedMeanings()
    const avoidChars = this.parseAvoidChars()

    if (style) params.style = style
    if (meanings.length) params.meanings = meanings
    if (avoidChars.length) params.avoid_chars = avoidChars

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
        wx.navigateTo({ url: '/pages/result/result' })
      }
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '起名失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
