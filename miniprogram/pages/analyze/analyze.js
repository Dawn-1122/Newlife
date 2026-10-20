/**
 * 释名 · 填姓名（可选补生辰）
 *
 * 与「起名」页同一套日期与时辰交互：自绘三列 scroll-view + 12 格时辰，
 * 不用原生 picker —— 预览环境里原生 picker 点不开，用户点日期没反应，
 * 会以为整页坏了。
 *
 * 性别也影响释名的用字评价（同一组字男女评价不同），故保留；但生辰仍是可选，
 * 关掉八字时只按用字、音律、五格与出处来释名。
 */

const api = require('../../utils/api')
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')
const ds = require('../../utils/date-sheet')
const hours = require('../../utils/hours')

Page({
  data: {
    fullName: '',
    useBazi: false,
    gender: 'male',
    birthDate: '',
    hourIndex: 8,
    hourText: hours.labelOf(8),
    hours: hours.HOURS,

    // 自绘弹层（null 表示未打开）；日期与时辰共用，靠 kind 区分画什么
    sheet: null,

    loading: false
  },

  onNameInput(e) {
    this.setData({ fullName: e.detail.value })
  },

  onGenderTap(e) {
    this.setData({ gender: e.currentTarget.dataset.gender })
  },

  onBaziToggle() {
    // 关掉八字时保留已选日期：用户可能只是临时对比，不想丢掉填过的生辰
    this.setData({ useBazi: !this.data.useBazi })
  },

  // 时辰与日期用同一个弹层：点一行 → 底部弹层选一列 → 确定回填
  onOpenHour() {
    this.setData({
      sheet: {
        kind: 'hour',
        title: '出生时辰',
        hour: this.data.hourIndex,
        hourAnchor: 'h' + this.data.hourIndex
      }
    })
  },

  onPickHour(e) {
    const idx = Number(e.currentTarget.dataset.idx)
    this.setData({
      sheet: Object.assign({}, this.data.sheet, { hour: idx, hourAnchor: 'h' + idx })
    })
  },

  // ── 弹层（日期 / 时辰共用） ──

  onOpenBirthDate() {
    const now = new Date()
    this.setData({
      sheet: Object.assign(
        ds.build({
          value: this.data.birthDate,
          // 释名多是给已经出生的孩子或自己算，默认今天最省事
          fallback: ds.today(),
          minYear: ds.MIN_YEAR,
          maxYear: now.getFullYear(),
          title: '出生日期'
        }),
        // kind 决定弹层里画三列日期还是单列时辰
        { kind: 'date' }
      )
    })
  },

  onPickYear(e) {
    this.setData({ sheet: ds.withYear(this.data.sheet, Number(e.currentTarget.dataset.v)) })
  },

  onPickMonth(e) {
    this.setData({ sheet: ds.withMonth(this.data.sheet, Number(e.currentTarget.dataset.v)) })
  },

  onPickDay(e) {
    this.setData({ sheet: ds.withDay(this.data.sheet, Number(e.currentTarget.dataset.v)) })
  },

  onSheetCancel() {
    this.setData({ sheet: null })
  },

  onSheetConfirm() {
    const sheet = this.data.sheet
    if (!sheet) return
    if (sheet.kind === 'hour') {
      this.setData({
        hourIndex: sheet.hour,
        hourText: hours.labelOf(sheet.hour),
        sheet: null
      })
      return
    }
    this.setData({ birthDate: ds.format(sheet), sheet: null })
  },

  // 弹层内部点击不应关掉弹层（catchtap 只是止血，真正的关闭只有取消/确定）
  noop() {},

  async onSubmit() {
    const fullName = (this.data.fullName || '').trim()
    if (fullName.length < 2) {
      wx.showToast({ title: '请输入至少2个字的姓名', icon: 'none' })
      return
    }
    if (fullName.length > 10) {
      wx.showToast({ title: '姓名最多 10 个字', icon: 'none' })
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
      params.year = Number(parts[0])
      params.month = Number(parts[1])
      params.day = Number(parts[2])
      params.hour = hours.hourOf(this.data.hourIndex)
    }

    this.setData({ loading: true })
    try {
      const result = await api.analyzeName(params)
      const app = getApp()
      app.globalData.analyzeResult = result
      app.globalData.lastParams = params
      // 收进「名字本」（本机存储）；存失败只提示，不阻断查看结果
      const saved = namebook.addRecord(namebook.buildRecord('analyze', params, result, 0))
      if (!saved.ok) {
        wx.showToast({ title: saved.error, icon: 'none' })
      }
      wx.navigateTo({ url: '/pages/analyze-result/analyze-result' })
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '测评失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
