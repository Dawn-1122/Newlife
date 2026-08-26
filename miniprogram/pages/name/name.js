const api = require('../../utils/api')

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

    // 共享（性别）
    gender: 'male',

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

  onIndustryChange(e) {
    const index = Number(e.detail.value)
    const opt = this.data.industryOptions[index]
    this.setData({
      industry: opt.code,
      industryName: opt.name
    })
  },

  onNext() {
    const app = getApp()

    if (this.data.tab === 'prenatal') {
      if (!this.data.dueDate) {
        wx.showToast({ title: '请选择预产期', icon: 'none' })
        return
      }
      app.globalData.draftParams = {
        due_date: this.data.dueDate,
        range_days: this.data.rangeDays,
        gender: this.data.gender
      }
      app.globalData.draftTab = 'prenatal'
    } else {
      const surname = (this.data.surname || '').trim()
      if (!surname) {
        wx.showToast({ title: '请输入姓氏', icon: 'none' })
        return
      }
      if (this.data.useBazi && !this.data.birthDate) {
        wx.showToast({ title: '请选择出生日期', icon: 'none' })
        return
      }

      const draft = {
        surname: surname,
        gender: this.data.gender,
        name_length: this.data.nameLength,
        max_results: 50,
        use_bazi: this.data.useBazi,
        use_poetry: true,
        // 展示用字段（提交时会剥离，不透传给后端）
        birthDate: this.data.birthDate,
        hourText: this.data.hourOptions[this.data.hourIndex]
      }

      if (this.data.useBazi && this.data.birthDate) {
        const parts = this.data.birthDate.split('-')
        const hourMap = [23, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]
        draft.year = Number(parts[0])
        draft.month = Number(parts[1])
        draft.day = Number(parts[2])
        draft.hour = hourMap[this.data.hourIndex]
      }
      if (this.data.industry) draft.industry = this.data.industry

      app.globalData.draftParams = draft
      app.globalData.draftTab = 'postnatal'
    }

    wx.navigateTo({ url: '/pages/wizard/wizard' })
  }
})
