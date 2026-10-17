const api = require('../../utils/api')
const share = require('../../utils/share')

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
    generationalChar: '',

    // 产前（预产期）
    dueDate: '',
    rangeDays: api.DEFAULT_RANGE_DAYS,
    rangeOptions: api.RANGE_OPTIONS,

    // 共享（性别）
    gender: 'male',

    loading: false
  },

  onLoad(options) {
    // 支持从二级菜单「孕期参考起名」直达产前分支
    if (options && options.tab === 'prenatal') {
      this.setData({ tab: 'prenatal' })
    }
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

  onGenerationalInput(e) {
    this.setData({ generationalChar: e.detail.value })
  },

  onRangeTap(e) {
    this.setData({ rangeDays: Number(e.currentTarget.dataset.range) })
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
      if (surname.length > 4) {
        wx.showToast({ title: '姓氏最多 4 个字', icon: 'none' })
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

      // 字辈：仅双字名生效，固定在名字第二个字
      const genChar = (this.data.generationalChar || '').trim()
      if (this.data.nameLength === 2 && genChar) {
        draft.generational_char = genChar
      }

      if (this.data.useBazi && this.data.birthDate) {
        const parts = this.data.birthDate.split('-')
        const hourMap = [23, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]
        draft.year = Number(parts[0])
        draft.month = Number(parts[1])
        draft.day = Number(parts[2])
        draft.hour = hourMap[this.data.hourIndex]
      }
      app.globalData.draftParams = draft
      app.globalData.draftTab = 'postnatal'
    }

    wx.navigateTo({ url: '/pages/wizard/wizard' })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
