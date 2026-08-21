const api = require('../../utils/api')

function buildStyleOptions() {
  return (api.STYLE_OPTIONS || []).map(function (s) {
    return { code: s.code, name: s.name, selected: false }
  })
}

function buildMeaningOptions() {
  return (api.MEANING_OPTIONS || []).map(function (m) {
    return { code: m.code, name: m.name, selected: false }
  })
}

Page({
  data: {
    tab: 'postnatal', // postnatal | prenatal

    // 产后（精确生辰）
    surname: '',
    useBazi: true,
    birthDate: '',
    hourIndex: 8,
    hourOptions: [
      '子时 (23-1点)', '丑时 (1-3点)', '寅时 (3-5点)', '卯时 (5-7点)',
      '辰时 (7-9点)', '巳时 (9-11点)', '午时 (11-13点)', '未时 (13-15点)',
      '申时 (15-17点)', '酉时 (17-19点)', '戌时 (19-21点)', '亥时 (21-23点)'
    ],
    nameLength: 2,

    // 产前（预产期）
    dueDate: '',
    rangeDays: api.DEFAULT_RANGE_DAYS,
    rangeOptions: api.RANGE_OPTIONS,

    // 共享（性别 / 风格 / 寓意 / 避讳）
    gender: 'male',
    styleOptions: buildStyleOptions(),
    meaningOptions: buildMeaningOptions(),
    avoidChars: '',

    // 行业（产后可选，P0 透传）
    industry: '',
    industryName: '不限',
    industryOptions: [
      { code: '', name: '不限' },
      { code: 'tech', name: '互联网/科技' },
      { code: 'media', name: '传媒/文创' },
      { code: 'catering', name: '餐饮' },
      { code: 'energy', name: '能源' },
      { code: 'finance', name: '金融/财会' },
      { code: 'law', name: '法律' },
      { code: 'manufacturing', name: '制造/工业' },
      { code: 'education', name: '教育/文化' },
      { code: 'medical', name: '医疗/健康' },
      { code: 'art', name: '艺术' },
      { code: 'agriculture', name: '农业' },
      { code: 'realestate', name: '地产/建筑' },
      { code: 'trade', name: '贸易/物流' },
      { code: 'tourism', name: '旅游/服务' }
    ],

    loading: false
  },

  onTabTap(e) {
    this.setData({ tab: e.currentTarget.dataset.tab })
  },

  onSurnameInput(e) {
    this.setData({ surname: e.detail.value })
  },

  onGenderTap(e) {
    this.setData({ gender: e.currentTarget.dataset.gender })
  },

  onBaziSwitch(e) {
    this.setData({ useBazi: e.detail.value })
  },

  onDateChange(e) {
    this.setData({ birthDate: e.detail.value })
  },

  onDueDateChange(e) {
    this.setData({ dueDate: e.detail.value })
  },

  onHourChange(e) {
    this.setData({ hourIndex: Number(e.detail.value) })
  },

  onLengthTap(e) {
    this.setData({ nameLength: parseInt(e.currentTarget.dataset.length, 10) })
  },

  onRangeTap(e) {
    this.setData({ rangeDays: Number(e.currentTarget.dataset.range) })
  },

  onStyleTap(e) {
    const code = e.currentTarget.dataset.code
    const styleOptions = this.data.styleOptions.map(function (s) {
      return { code: s.code, name: s.name, selected: s.code === code }
    })
    this.setData({ styleOptions })
  },

  onMeaningTap(e) {
    const code = e.currentTarget.dataset.code
    let selectedCount = 0
    this.data.meaningOptions.forEach(function (m) {
      if (m.selected) selectedCount += 1
    })

    const meaningOptions = this.data.meaningOptions.map(function (m) {
      if (m.code === code) {
        // 已选中则取消；未选中且未达上限则选中
        if (m.selected) {
          return { code: m.code, name: m.name, selected: false }
        }
        if (selectedCount < api.MEANING_MAX_SELECT) {
          return { code: m.code, name: m.name, selected: true }
        }
        wx.showToast({ title: '最多选择3个寓意', icon: 'none' })
      }
      return m
    })
    this.setData({ meaningOptions })
  },

  onAvoidInput(e) {
    this.setData({ avoidChars: e.detail.value })
  },

  onIndustryChange(e) {
    const index = Number(e.detail.value)
    const opt = this.data.industryOptions[index]
    this.setData({
      industry: opt.code,
      industryName: opt.name
    })
  },

  getSelectedStyle() {
    let result = ''
    this.data.styleOptions.forEach(function (s) {
      if (s.selected) result = s.code
    })
    return result
  },

  getSelectedMeanings() {
    const result = []
    this.data.meaningOptions.forEach(function (m) {
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

  async onSubmit() {
    if (this.data.tab === 'prenatal') {
      this.submitPrenatal()
    } else {
      this.submitPostnatal()
    }
  },

  async submitPrenatal() {
    if (!this.data.dueDate) {
      wx.showToast({ title: '请选择预产期', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    try {
      const result = await api.prenatal({
        due_date: this.data.dueDate,
        range_days: this.data.rangeDays,
        gender: this.data.gender
      })
      const app = getApp()
      app.globalData.prenatalResult = result
      wx.navigateTo({ url: '/pages/prenatal-result/prenatal-result' })
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '查询失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  async submitPostnatal() {
    const surname = (this.data.surname || '').trim()
    if (!surname) {
      wx.showToast({ title: '请输入姓氏', icon: 'none' })
      return
    }
    if (this.data.useBazi && !this.data.birthDate) {
      wx.showToast({ title: '请选择出生日期', icon: 'none' })
      return
    }

    const params = {
      surname: surname,
      gender: this.data.gender,
      name_length: this.data.nameLength,
      max_results: 20,
      use_bazi: this.data.useBazi,
      use_poetry: true
    }

    if (this.data.useBazi && this.data.birthDate) {
      const parts = this.data.birthDate.split('-')
      const hourMap = [23, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]
      params.year = Number(parts[0])
      params.month = Number(parts[1])
      params.day = Number(parts[2])
      params.hour = hourMap[this.data.hourIndex]
    }

    const style = this.getSelectedStyle()
    const meanings = this.getSelectedMeanings()
    const avoidChars = this.parseAvoidChars()

    if (style) params.style = style
    if (meanings.length) params.meanings = meanings
    if (avoidChars.length) params.avoid_chars = avoidChars
    if (this.data.industry) params.industry = this.data.industry

    this.setData({ loading: true })
    try {
      const result = await api.generateNames(params)
      const app = getApp()
      app.globalData.lastResult = result
      app.globalData.lastParams = { surname, gender: this.data.gender, useBazi: this.data.useBazi }
      wx.navigateTo({ url: '/pages/result/result' })
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '起名失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
