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

// 起名方式卡（寓意优先 / 命格优先）
function buildModes(selected) {
  return [
    {
      code: 'meaning_first',
      name: '寓意优先',
      desc: '先从诗词经典里挑你喜欢的意境来源，再结合八字在这些来源里定字',
      selected: selected === 'meaning_first'
    },
    {
      code: 'bazi_first',
      name: '命格优先',
      desc: '先看命理喜用与起名方向，再据此推荐契合命格的意境来源',
      selected: selected === 'bazi_first'
    }
  ]
}

// 动态步骤标题
const STEP_TITLES = {
  mode: '选择方式',
  style: '选择风格',
  meaning: '选择寓意',
  avoid: '避讳字',
  confirm: '确认信息',
  sources: '选意境来源',
  chars: '精选用字'
}

Page({
  data: {
    step: 1,
    totalSteps: 4,
    stepKey: 'style',
    stepTitle: '',
    stepKeys: [],
    progress: 0,
    tab: 'postnatal',
    mode: 'meaning_first',
    modes: [],
    styles: [],
    meanings: [],
    avoidChars: '',
    selectedStyleName: '',
    selectedMeaningNames: [],
    selectedMeaningText: '',
    baseLines: [],
    loading: false,
    // 两模式流程（仅产后 + 八字）
    needCharStep: false,
    sourceLoading: false,
    sources: [],
    baziExplanation: null,
    selectedSourceCount: 0,
    charLoading: false,
    sourceCharGroups: [],
    selectedCharCount: 0
  },

  onLoad() {
    const app = getApp()
    this.draft = app.globalData.draftParams || {}
    const tab = app.globalData.draftTab || (this.draft.due_date ? 'prenatal' : 'postnatal')

    const style = this.draft.style || ''
    const meanings = this.draft.meanings || []
    const avoidChars = (this.draft.avoid_chars || []).join(',')

    // 仅产后且提供完整生辰时，才走「两模式：来源 → 选字」流程
    const needCharStep = tab === 'postnatal' && !!(this.draft.year && this.draft.month && this.draft.day)

    const stepKeys = needCharStep
      ? ['mode', 'style', 'meaning', 'avoid', 'confirm', 'sources', 'chars']
      : ['style', 'meaning', 'avoid', 'confirm']

    this.setData({
      tab: tab,
      stepKeys: stepKeys,
      totalSteps: stepKeys.length,
      needCharStep: needCharStep,
      modes: buildModes('meaning_first'),
      styles: buildStyles(style),
      meanings: buildMeanings(meanings),
      avoidChars: avoidChars
    })
    this.goStep(1)
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

  goStep(step) {
    const total = this.data.stepKeys.length
    const clamped = Math.max(1, Math.min(total, step))
    const stepKey = this.data.stepKeys[clamped - 1]
    this.setData({
      step: clamped,
      stepKey: stepKey,
      stepTitle: STEP_TITLES[stepKey] || '',
      progress: Math.round(clamped / total * 100)
    })
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

    if (this.data.needCharStep) {
      const modeName = this.data.mode === 'bazi_first' ? '命格优先' : '寓意优先'
      baseLines.push({ label: '起名方式', value: modeName })
    }

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

  onModeTap(e) {
    const code = e.currentTarget.dataset.code
    this.setData({ modes: buildModes(code), mode: code })
    this.refreshSummary()
  },

  onNext() {
    const cur = this.data.stepKey
    if (cur === 'confirm') {
      if (this.data.needCharStep) {
        this.goStep(this.data.step + 1)
        if (this.sourceQueryKey() !== this.lastSourceKey) this.loadSources()
      } else {
        this.onSubmit()
      }
      return
    }
    if (cur === 'sources') {
      if (this.getSelectedSourceIds().length === 0) {
        wx.showToast({ title: '请至少选择一个意境来源', icon: 'none' })
        return
      }
      this.goStep(this.data.step + 1)
      if (this.getSelectedSourceKey() !== this.lastCharSourceKey) this.loadSourceChars()
      return
    }
    this.goStep(this.data.step + 1)
  },

  onPrev() {
    this.goStep(this.data.step - 1)
  },

  onSkip() {
    const cur = this.data.stepKey
    if (cur === 'sources' || cur === 'chars') {
      this.onSubmit()
    } else {
      this.onNext()
    }
  },

  onJumpStep(e) {
    const key = e.currentTarget.dataset.key
    const idx = this.data.stepKeys.indexOf(key)
    if (idx >= 0) this.goStep(idx + 1)
  },

  sourceQueryKey() {
    return [
      this.data.mode,
      this.getSelectedMeanings().slice().sort().join(','),
      (this.data.avoidChars || '').trim()
    ].join('|')
  },

  getSelectedSourceIds() {
    const ids = []
    this.data.sources.forEach(function (s) {
      if (s.selected) ids.push(s.id)
    })
    return ids
  },

  getSelectedSourceKey() {
    return this.getSelectedSourceIds().slice().sort().join(',')
  },

  async loadSources() {
    const draft = this.draft || {}
    this.setData({ sourceLoading: true })
    try {
      const params = {
        surname: draft.surname,
        gender: draft.gender || 'male',
        year: draft.year,
        month: draft.month,
        day: draft.day,
        hour: draft.hour,
        mode: this.data.mode,
        meanings: this.getSelectedMeanings(),
        avoid_chars: this.parseAvoidChars(),
        limit: 20
      }
      const result = await api.recommendSources(params)
      const sources = (result.sources || []).map(function (s) {
        s.selected = false
        return s
      })
      const exp = result.bazi_explanation || null
      if (exp) {
        exp.xi_wuxing_text = (exp.xi_wuxing || []).join('、') || '—'
        exp.ji_wuxing_text = (exp.ji_wuxing || []).join('、') || ''
      }
      this.setData({
        sources: sources,
        baziExplanation: exp,
        sourceLoading: false,
        selectedSourceCount: 0
      })
      this.lastSourceKey = this.sourceQueryKey()
    } catch (err) {
      this.setData({ sourceLoading: false })
      wx.showToast({ title: '意境来源加载失败', icon: 'none' })
    }
  },

  onSourceTap(e) {
    const idx = Number(e.currentTarget.dataset.index)
    const source = this.data.sources[idx]
    const next = !source.selected
    this.setData({ ['sources[' + idx + '].selected']: next })
    this.setData({ selectedSourceCount: this.getSelectedSourceIds().length })
  },

  async loadSourceChars() {
    const draft = this.draft || {}
    this.setData({ charLoading: true })
    try {
      const params = {
        surname: draft.surname,
        gender: draft.gender || 'male',
        year: draft.year,
        month: draft.month,
        day: draft.day,
        hour: draft.hour,
        source_ids: this.getSelectedSourceIds(),
        limit_per_source: 8
      }
      const result = await api.sourceChars(params)
      const groups = (result.sources || []).map(function (s) {
        return {
          id: s.id,
          source: s.source,
          title: s.title,
          text: s.text,
          wuxing_tendency: s.wuxing_tendency,
          chars: (s.chars || []).map(function (c) {
            c.selected = false
            return c
          })
        }
      })
      this.setData({ sourceCharGroups: groups, charLoading: false, selectedCharCount: 0 })
      this.lastCharSourceKey = this.getSelectedSourceKey()
    } catch (err) {
      this.setData({ charLoading: false })
      wx.showToast({ title: '选字加载失败', icon: 'none' })
    }
  },

  getSelectedChars() {
    const chars = []
    this.data.sourceCharGroups.forEach(function (g) {
      g.chars.forEach(function (c) {
        if (c.selected) chars.push(c.char)
      })
    })
    return chars
  },

  getSelectedSourceChars() {
    const chars = []
    const seen = {}
    this.data.sources.forEach(function (s) {
      if (!s.selected) return
      ;(s.recommend_chars || []).forEach(function (c) {
        if (!seen[c]) {
          seen[c] = true
          chars.push(c)
        }
      })
    })
    return chars
  },

  onCharTap(e) {
    const gi = Number(e.currentTarget.dataset.gi)
    const ci = Number(e.currentTarget.dataset.ci)
    const char = this.data.sourceCharGroups[gi].chars[ci]
    const next = !char.selected
    if (next && this.getSelectedChars().length >= 6) {
      wx.showToast({ title: '最多选 6 个字', icon: 'none' })
      return
    }
    this.setData({
      ['sourceCharGroups[' + gi + '].chars[' + ci + '].selected']: next
    })
    this.setData({ selectedCharCount: this.getSelectedChars().length })
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

    // 来源约束：优先用所选字，否则用所选来源的推荐字并集
    const selectedChars = this.getSelectedChars()
    if (selectedChars.length) {
      params.selected_chars = selectedChars
    } else if (this.data.needCharStep) {
      const sourceChars = this.getSelectedSourceChars()
      if (sourceChars.length) params.selected_chars = sourceChars
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
  }
})
