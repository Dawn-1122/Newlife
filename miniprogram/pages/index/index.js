const api = require('../../utils/api')

Page({
  data: {
    surname: '',
    gender: 'male',
    useBazi: true,
    birthDate: '',
    hourIndex: 8, // 默认午时
    hourOptions: [
      '子时 (23-1点)', '丑时 (1-3点)', '寅时 (3-5点)', '卯时 (5-7点)',
      '辰时 (7-9点)', '巳时 (9-11点)', '午时 (11-13点)', '未时 (13-15点)',
      '申时 (15-17点)', '酉时 (17-19点)', '戌时 (19-21点)', '亥时 (21-23点)'
    ],
    nameLength: 2,
    loading: false
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

  onHourChange(e) {
    this.setData({ hourIndex: e.detail.value })
  },

  onLengthTap(e) {
    this.setData({ nameLength: parseInt(e.currentTarget.dataset.length) })
  },

  async onGenerateTap() {
    const { surname, gender, useBazi, birthDate, hourIndex, nameLength } = this.data

    if (!surname.trim()) {
      wx.showToast({ title: '请输入姓氏', icon: 'none' })
      return
    }

    if (useBazi && !birthDate) {
      wx.showToast({ title: '请选择出生日期', icon: 'none' })
      return
    }

    // 解析出生日期和时辰
    let params = {
      surname: surname.trim(),
      gender: gender,
      name_length: nameLength,
      max_results: 20,
      use_bazi: useBazi,
      use_poetry: true
    }

    if (useBazi && birthDate) {
      const [year, month, day] = birthDate.split('-').map(Number)
      // 时辰索引对应小时：子时=23或0，丑时=1...
      const hourMap = [23, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]
      params.year = year
      params.month = month
      params.day = day
      params.hour = hourMap[hourIndex]
    }

    this.setData({ loading: true })

    try {
      const result = await api.generateNames(params)
      
      // 缓存结果到全局
      const app = getApp()
      app.globalData.lastResult = result
      app.globalData.lastParams = { surname: surname.trim(), gender, useBazi }

      wx.navigateTo({
        url: '/pages/result/result'
      })
    } catch (err) {
      wx.showToast({
        title: err.message || '起名失败，请重试',
        icon: 'none'
      })
    } finally {
      this.setData({ loading: false })
    }
  }
})
