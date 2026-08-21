const api = require('../../utils/api')

Page({
  data: {
    fullName: '',
    useBazi: false,
    gender: 'male',
    birthDate: '',
    hourIndex: 8,
    hourOptions: [
      '子时 (23-1点)', '丑时 (1-3点)', '寅时 (3-5点)', '卯时 (5-7点)',
      '辰时 (7-9点)', '巳时 (9-11点)', '午时 (11-13点)', '未时 (13-15点)',
      '申时 (15-17点)', '酉时 (17-19点)', '戌时 (19-21点)', '亥时 (21-23点)'
    ],
    loading: false
  },

  onNameInput(e) {
    this.setData({ fullName: e.detail.value })
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
    this.setData({ hourIndex: Number(e.detail.value) })
  },

  async onSubmit() {
    const fullName = (this.data.fullName || '').trim()
    if (fullName.length < 2) {
      wx.showToast({ title: '请输入至少2个字的姓名', icon: 'none' })
      return
    }
    if (this.data.useBazi && !this.data.birthDate) {
      wx.showToast({ title: '请选择出生日期', icon: 'none' })
      return
    }

    const params = {
      full_name: fullName,
      gender: this.data.gender
    }

    if (this.data.useBazi && this.data.birthDate) {
      const parts = this.data.birthDate.split('-')
      const hourMap = [23, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]
      params.year = Number(parts[0])
      params.month = Number(parts[1])
      params.day = Number(parts[2])
      params.hour = hourMap[this.data.hourIndex]
    }

    this.setData({ loading: true })
    try {
      const result = await api.analyzeName(params)
      const app = getApp()
      app.globalData.analyzeResult = result
      wx.navigateTo({ url: '/pages/analyze-result/analyze-result' })
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '测评失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  }
})
